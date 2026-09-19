"""Per-client rate limiting for credential endpoints.

Implemented as plain ASGI middleware so it runs before routing and before any
database work. The store is in-process: it protects a single worker. Running
multiple workers or replicas requires a shared store (e.g. Redis) so the limits
are enforced globally instead of per process.
"""
from __future__ import annotations

import json
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


def _client_ip(scope: Scope) -> str:
    if app_config.TRUST_PROXY_HEADERS:
        for name, value in scope.get("headers") or []:  # type: ignore[union-attr]
            if name == b"x-forwarded-for":
                decoded = value.decode("latin-1") if isinstance(value, bytes) else str(value)
                first = decoded.split(",")[0].strip()
                if first:
                    return first

    client = scope.get("client")
    if isinstance(client, (tuple, list)) and client:
        return str(client[0])
    return "unknown"


def _normalise_path(path: str) -> str:
    # Routes may be registered with or without a trailing slash.
    return path.rstrip("/") or "/"


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
