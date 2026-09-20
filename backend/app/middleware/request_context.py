"""Attach a correlation id to every HTTP request and log one line per request.

The id is echoed back in the ``X-Request-ID`` response header (and, for a 500, in
the body), so a customer reporting "it failed with reference 5f3a91c2" maps
directly onto the traceback that :mod:`app.exception_handlers` wrote.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Awaitable, Callable, MutableMapping, Optional

from app.logging_config import reset_request_id, set_request_id

logger = logging.getLogger("litechat.access")

Scope = MutableMapping[str, object]
Message = MutableMapping[str, object]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

REQUEST_ID_HEADER = b"x-request-id"
# Only a client-supplied id that looks like an id is trusted; anything else is
# replaced, so a caller cannot inject newlines or megabytes into the log.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{4,64}$")
_QUIET_PATHS = frozenset({"/api/health"})


def _header(scope: Scope, name: bytes) -> Optional[str]:
    for key, value in scope.get("headers") or []:  # type: ignore[union-attr]
        if key == name:
            try:
                return value.decode("latin-1") if isinstance(value, bytes) else str(value)
            except Exception:  # pragma: no cover - decode of latin-1 cannot fail
                return None
    return None


def _client_ip(scope: Scope) -> str:
    client = scope.get("client")
    if isinstance(client, (tuple, list)) and client:
        return str(client[0])
    return "-"


class RequestContextMiddleware:
    """Correlation id + one access log line (with duration) per request."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        incoming = _header(scope, REQUEST_ID_HEADER)
        candidate = (incoming or "").strip()
        request_id = candidate if _SAFE_REQUEST_ID.match(candidate) else uuid.uuid4().hex[:12]
        token = set_request_id(request_id)

        path = str(scope.get("path", ""))
        method = str(scope.get("method", ""))
        status = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message.get("type") == "http.response.start":
                status = int(message.get("status") or 500)
                headers = list(message.get("headers") or [])
                headers.append((REQUEST_ID_HEADER, request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            # 5xx is an operator problem, everything else is routine traffic.
            level = logging.ERROR if status >= 500 else logging.INFO
            if path in _QUIET_PATHS:
                level = logging.DEBUG
            logger.log(
                level,
                "%s %s -> %s (%.1f ms, ip=%s)",
                method,
                path,
                status,
                elapsed_ms,
                _client_ip(scope),
            )
            reset_request_id(token)
