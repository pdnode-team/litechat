import json
import logging
from typing import Annotated
from litestar import websocket
from litestar.params import PathParameter
from litestar.connection import WebSocket
from app.db.session import async_session_factory
from app.models.ticket import Ticket
from app.services.auth_service import decode_access_token
from app.services.websocket_hub import hub, ConnectionInfo

logger = logging.getLogger("websocket_controller")

@websocket(path="/ws/tickets/{ticket_id:int}")
async def ticket_websocket_handler(socket: WebSocket, ticket_id: Annotated[int, PathParameter()]) -> None:
    await socket.accept()
    
    token = socket.query_params.get("token")
    if not token:
        await socket.close(code=4401, reason="Unauthorized: token missing")
        return

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        await socket.close(code=4401, reason="Unauthorized: invalid token")
        return

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        await socket.close(code=4401, reason="Unauthorized: malformed token subject")
        return
    user_name = payload.get("name", "User")
    role = payload.get("role", "customer")

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
                await hub.broadcast(
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
