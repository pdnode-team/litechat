import asyncio
import json
import logging
from typing import Dict, Set, Any, Optional
from litestar import WebSocket

logger = logging.getLogger("websocket_hub")

class ConnectionInfo:
    def __init__(self, socket: WebSocket, user_id: int, user_name: str, role: str, ticket_id: int):
        self.socket = socket
        self.user_id = user_id
        self.user_name = user_name
        self.role = role
        self.ticket_id = ticket_id

class WebSocketHub:
    def __init__(self):
        # ticket_id -> Set[ConnectionInfo]
        self._rooms: Dict[int, Set[ConnectionInfo]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, conn: ConnectionInfo) -> None:
        async with self._lock:
            if conn.ticket_id not in self._rooms:
                self._rooms[conn.ticket_id] = set()
            self._rooms[conn.ticket_id].add(conn)
            logger.info(f"User {conn.user_name} ({conn.role}) connected to ticket {conn.ticket_id}")

        # Broadcast user joined system event to room
        await self.broadcast(
            conn.ticket_id,
            {
                "type": "presence",
                "event": "joined",
                "user_id": conn.user_id,
                "user_name": conn.user_name,
                "role": conn.role,
            },
        )

    async def disconnect(self, conn: ConnectionInfo) -> None:
        async with self._lock:
            if conn.ticket_id in self._rooms:
                self._rooms[conn.ticket_id].discard(conn)
                if not self._rooms[conn.ticket_id]:
                    del self._rooms[conn.ticket_id]
            logger.info(f"User {conn.user_name} disconnected from ticket {conn.ticket_id}")

        await self.broadcast(
            conn.ticket_id,
            {
                "type": "presence",
                "event": "left",
                "user_id": conn.user_id,
                "user_name": conn.user_name,
                "role": conn.role,
            },
        )

    async def broadcast(self, ticket_id: int, data: Dict[str, Any], exclude_socket: Optional[WebSocket] = None) -> None:
        connections = list(self._rooms.get(ticket_id, set()))
        if not connections:
            return

        msg_obj = data.get("message")
        is_whisper = (
            data.get("message_type") == "whisper"
            or (isinstance(msg_obj, dict) and msg_obj.get("message_type") == "whisper")
        )
        text_data = json.dumps(data)

        for conn in connections:
            if exclude_socket and conn.socket == exclude_socket:
                continue

            # Whisper messages are strictly hidden from customers
            if is_whisper and conn.role == "customer":
                continue

            try:
                await conn.socket.send_text(text_data)
            except Exception as exc:
                logger.warning(f"Error sending message to client {conn.user_name}: {exc}")

hub = WebSocketHub()
