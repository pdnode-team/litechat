"""Per-client rate limiting for credential endpoints.

Implemented as plain ASGI middleware so it runs before routing and before any
database work. The store is in-process: it protects a single worker. Running
multiple workers or replicas requires a shared store (e.g. Redis) so the limits
are enforced globally instead of per process.
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from typing import Awaitable, Callable, Deque, MutableMapping, Optional, Tuple

from litestar.status_codes import HTTP_429_TOO_MANY_REQUESTS

from app import config as app_config

Scope = MutableMapping[str, object]
Message = MutableMapping[str, object]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


class SlidingWindowLimiter:
    """Tracks request timestamps per key inside a rolling time window."""

    def __init__(self) -> None:
        self._hits: dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """Record a hit. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - window_seconds
        bucket = self._hits[key]

        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= max_requests:
            retry_after = max(1, int(window_seconds - (now - bucket[0])) + 1)
            return False, retry_after

        bucket.append(now)
        return True, 0

    def reset(self) -> None:
        """Drop all counters (used by tests)."""
        self._hits.clear()


limiter = SlidingWindowLimiter()


def _header_value(scope: Scope, header_name: bytes) -> Optional[str]:
    for name, value in scope.get("headers") or []:  # type: ignore[union-attr]
        if name == header_name:
            decoded = value.decode("latin-1") if isinstance(value, bytes) else str(value)
            return decoded.strip()
    return None


def _client_ip(scope: Scope) -> str:
    if app_config.TRUST_PROXY_HEADERS:
        # Traefik / most reverse proxies set X-Real-IP to the connecting client
        # and *append* to X-Forwarded-For. The leftmost XFF hop is attacker-
        # controlled, so it must not be the rate-limit key.
        real_ip = _header_value(scope, b"x-real-ip")
        if real_ip:
            return real_ip.split(",")[0].strip() or real_ip

        forwarded = _header_value(scope, b"x-forwarded-for")
        if forwarded:
            hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
            if hops:
                return hops[-1]

    client = scope.get("client")
    if isinstance(client, (tuple, list)) and client:
        return str(client[0])
    return "unknown"


def _normalise_path(path: str) -> str:
    # Routes may be registered with or without a trailing slash.
    return path.rstrip("/") or "/"


def _bearer_user_id(scope: Scope) -> Optional[int]:
    """Best-effort user id from the Authorization header.

    Rate limiting runs before authentication, so this only exists to tell the
    affected client why its request was rejected. A missing or invalid token
    simply means the notice is not delivered.
    """
    for name, value in scope.get("headers") or []:  # type: ignore[union-attr]
        if name != b"authorization":
            continue
        try:
            decoded = value.decode("latin-1") if isinstance(value, bytes) else str(value)
        except Exception:
            return None
        if not decoded.lower().startswith("bearer "):
            return None

        # Imported lazily so the middleware has no import-time dependency on the
        # auth stack (and so a token library issue cannot break rate limiting).
        from app.services.auth_service import decode_access_token

        payload = decode_access_token(decoded.split(" ", 1)[1].strip())
        if not payload or "sub" not in payload:
            return None
        try:
            return int(payload["sub"])
        except (TypeError, ValueError):
            return None
    return None


async def _publish_rate_limited(scope: Scope, path: str, retry_after: int) -> None:
    user_id = _bearer_user_id(scope)
    if user_id is None:
        return
    try:
        from app.services import events as event_bus
        from app.services.events import RATE_LIMITED, Event

        await event_bus.publish(
            Event(
                type=RATE_LIMITED,
                notification={"path": path, "retry_after": retry_after},
                user_ids=[user_id],
            )
        )
    except Exception:  # never let a notification failure mask the 429
        logging.getLogger("litechat.ratelimit").debug("Could not publish rate_limited", exc_info=True)


class RateLimitMiddleware:
    """ASGI middleware enforcing RATE_LIMIT_RULES on matching paths."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or not app_config.RATE_LIMIT_ENABLED:
            await self.app(scope, receive, send)
            return

        path = _normalise_path(str(scope.get("path", "")))
        rule: Optional[Tuple[int, int]] = app_config.RATE_LIMIT_RULES.get(path)
        if rule is None:
            await self.app(scope, receive, send)
            return

        max_requests, window_seconds = rule
        key = f"{path}:{_client_ip(scope)}"
        allowed, retry_after = limiter.check(key, max_requests, window_seconds)

        if not allowed:
            # Tell the affected client why, in real time, before rejecting it.
            await _publish_rate_limited(scope, path, retry_after)

            # Written as a raw ASGI response: this middleware runs before the
            # router, so it must not depend on Litestar's response machinery.
            body = json.dumps(
                {
                    "status_code": HTTP_429_TOO_MANY_REQUESTS,
                    "detail": "Too many requests. Please slow down and try again shortly.",
                }
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": HTTP_429_TOO_MANY_REQUESTS,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"retry-after", str(retry_after).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
