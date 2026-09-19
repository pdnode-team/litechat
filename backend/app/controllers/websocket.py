import json
import logging
from typing import Annotated, Optional

from litestar import websocket
from litestar.connection import WebSocket
from litestar.params import PathParameter

from app.db.session import async_session_factory
from app.models.ticket import Ticket
from app.models.user import User
from app.services.auth_service import decode_access_token
from app.services.websocket_hub import ConnectionInfo, hub

logger = logging.getLogger("websocket_controller")


def _token_user_id(socket: WebSocket) -> Optional[int]:
    """Decode the ``token`` query parameter into a user id."""
    token = socket.query_params.get("token")
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None

    try:
        return int(payload["sub"])
    except (TypeError, ValueError):
        return None


async def _authenticate(socket: WebSocket) -> Optional[User]:
    """Resolve the connection's user from the database, not the token claims.

    Room membership (``staff``/``admin``) depends on the role, and a role change
    must take effect without waiting for the token to expire.
    """
    user_id = _token_user_id(socket)
    if user_id is None:
        return None

    async with async_session_factory() as session:
        user = await session.get(User, user_id)

    if user is None or not user.is_active:
        return None
    return user


@websocket(path="/ws/tickets/{ticket_id:int}")
async def ticket_websocket_handler(socket: WebSocket, ticket_id: Annotated[int, PathParameter()]) -> None:
    """Per-ticket conversation channel: messages, typing and presence."""
    await socket.accept()

    user = await _authenticate(socket)
    if user is None:
        await socket.close(code=4401, reason="Unauthorized: invalid token")
        return

    user_id, user_name, role = user.id, user.full_name, user.role

    async with async_session_factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            await socket.close(code=4404, reason="Ticket not found")
            return
        if role == "customer" and ticket.customer_id != user_id:
            await socket.close(code=4403, reason="Forbidden: access denied to ticket")
            return

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
    await socket.accept()

    user = await _authenticate(socket)
    if user is None:
        await socket.close(code=4401, reason="Unauthorized: invalid token")
        return

    conn = ConnectionInfo(
        socket=socket,
        user_id=user.id,
        user_name=user.full_name,
        role=user.role,
        ticket_id=None,
        scope="user",
    )
    await hub.connect(conn)

    # Tell the client what it is subscribed to; useful for debugging and for
    # the UI to know whether it will receive staff/admin events.
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
