import json
import logging
from typing import Annotated, Optional

from litestar import websocket
from litestar.connection import WebSocket
from litestar.params import PathParameter

from app.controllers.auth import get_user_from_token
from app.db.session import async_session_factory
from app.middleware.rate_limit import limiter
from app.models.ticket import Ticket
from app.models.user import User
from app.services.access import require_ticket_view
from app.services.websocket_hub import ConnectionInfo, hub

logger = logging.getLogger("websocket_controller")

WS_CONNECT_LIMIT = 30
WS_CONNECT_WINDOW = 60


def _token_from_socket(socket: WebSocket) -> Optional[str]:
    token = socket.query_params.get("token")
    return token.strip() if token else None


async def _authenticate(socket: WebSocket) -> Optional[User]:
    token = _token_from_socket(socket)
    if not token:
        return None
    return await get_user_from_token(token)


@websocket(path="/ws/tickets/{ticket_id:int}")
async def ticket_websocket_handler(socket: WebSocket, ticket_id: Annotated[int, PathParameter()]) -> None:
    """Per-ticket conversation channel: messages, typing and presence."""
    user = await _authenticate(socket)
    if user is None:
        await socket.close(code=4401, reason="Unauthorized: invalid token")
        return

    allowed, _ = limiter.check(f"ws:{user.id}", WS_CONNECT_LIMIT, WS_CONNECT_WINDOW)
    if not allowed:
        await socket.close(code=4429, reason="Too many connections")
        return

    user_id, user_name, role = user.id, user.full_name, user.role

    async with async_session_factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        try:
            require_ticket_view(user, ticket)
        except Exception:
            await socket.close(code=4404, reason="Ticket not found")
            return

    await socket.accept()

    conn = ConnectionInfo(
        socket=socket,
        user_id=user_id,
        user_name=user_name,
        role=role,
        ticket_id=ticket_id,
        scope="ticket",
    )
    await hub.connect(conn)

    try:
        while True:
            data_text = await socket.receive_text()
            try:
                data = json.loads(data_text)
            except Exception:
                continue

            event_type = data.get("type")
            if event_type == "typing":
                await hub.broadcast_ticket(
                    ticket_id,
                    {
                        "type": "typing",
                        "user_id": user_id,
                        "user_name": user_name,
                        "is_typing": bool(data.get("is_typing", False)),
                    },
                    exclude_socket=socket,
                )
            elif event_type == "ping":
                await socket.send_text(json.dumps({"type": "pong"}))

    except Exception as exc:
        logger.debug(f"WebSocket closed or errored: {exc}")
    finally:
        await hub.disconnect(conn)


@websocket(path="/ws/notifications")
async def notifications_websocket_handler(socket: WebSocket) -> None:
    """Account-wide channel.

    Every state change the user is allowed to know about is pushed here, so the
    UI never has to poll: new tickets in the queue, status and assignment
    changes, role and account updates, catalogue edits, ratings and rate-limit
    notices.
    """
    user = await _authenticate(socket)
    if user is None:
        await socket.close(code=4401, reason="Unauthorized: invalid token")
        return

    allowed, _ = limiter.check(f"ws:{user.id}", WS_CONNECT_LIMIT, WS_CONNECT_WINDOW)
    if not allowed:
        await socket.close(code=4429, reason="Too many connections")
        return

    await socket.accept()

    conn = ConnectionInfo(
        socket=socket,
        user_id=user.id,
        user_name=user.full_name,
        role=user.role,
        ticket_id=None,
        scope="user",
    )
    await hub.connect(conn)

    await socket.send_text(
        json.dumps(
            {
                "type": "ready",
                "user_id": user.id,
                "role": user.role,
                "channels": ["user"] + (["staff"] if conn.is_staff else []) + (["admin"] if conn.is_admin else []),
            }
        )
    )

    try:
        while True:
            data_text = await socket.receive_text()
            try:
                data = json.loads(data_text)
            except Exception:
                continue
            if data.get("type") == "ping":
                await socket.send_text(json.dumps({"type": "pong"}))

    except Exception as exc:
        logger.debug(f"Notification socket closed or errored: {exc}")
    finally:
        await hub.disconnect(conn)
