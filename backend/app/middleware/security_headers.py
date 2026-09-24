"""Security headers ASGI middleware (defense-in-depth)."""
from __future__ import annotations

from typing import Awaitable, Callable, MutableMapping

Scope = MutableMapping[str, object]
Message = MutableMapping[str, object]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


class SecurityHeadersMiddleware:
    """Adds standard defense-in-depth HTTP headers to all responses."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                raw_headers = list(message.get("headers") or [])
                existing = {k.lower() for k, _ in raw_headers}

                if b"x-content-type-options" not in existing:
                    raw_headers.append((b"x-content-type-options", b"nosniff"))
                if b"x-frame-options" not in existing:
                    raw_headers.append((b"x-frame-options", b"SAMEORIGIN"))
                if b"referrer-policy" not in existing:
                    raw_headers.append((b"referrer-policy", b"strict-origin-when-cross-origin"))

                message["headers"] = raw_headers

            await send(message)

        await self.app(scope, receive, send_wrapper)
