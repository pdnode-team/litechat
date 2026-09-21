"""In-process WebSocket fan-out.

Connections live in one of several rooms:

* ``ticket:<id>``  — the conversation view for a single ticket
* ``user:<id>``    — one user's notification stream (all their tickets, account events)
* ``staff``        — every connected agent and admin (queue-wide events)
* ``admin``        — connected administrators only (configuration events)

The hub only moves bytes; which event goes to which room is decided in
``app/services/events.py``.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Iterable, Optional, Set

from litestar import WebSocket

logger = logging.getLogger("websocket_hub")

STAFF_ROLES = ("agent", "admin")


class ConnectionInfo:
    def __init__(
        self,
        socket: WebSocket,
        user_id: int,
        user_name: str,
        role: str,
        ticket_id: Optional[int] = None,
        scope: str = "ticket",
    ):
        self.socket = socket
        self.user_id = user_id
        self.user_name = user_name
        self.role = role
        self.ticket_id = ticket_id
        # "ticket" for /ws/tickets/{id}, "user" for /ws/notifications
        self.scope = scope

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ConnectionInfo user={self.user_id} role={self.role} scope={self.scope}>"


class WebSocketHub:
    def __init__(self) -> None:
        self._ticket_rooms: Dict[int, Set[ConnectionInfo]] = {}
        self._user_rooms: Dict[int, Set[ConnectionInfo]] = {}
        self._staff: Set[ConnectionInfo] = set()
        self._admins: Set[ConnectionInfo] = set()
        self._lock = asyncio.Lock()

    # ── registration ─────────────────────────────────────────────────────
    async def connect(self, conn: ConnectionInfo) -> None:
        async with self._lock:
            if conn.scope == "ticket" and conn.ticket_id is not None:
                self._ticket_rooms.setdefault(conn.ticket_id, set()).add(conn)
            else:
                self._user_rooms.setdefault(conn.user_id, set()).add(conn)
                if conn.is_staff:
                    self._staff.add(conn)
                if conn.is_admin:
                    self._admins.add(conn)

        logger.info(
            "ws connect user=%s role=%s scope=%s ticket=%s",
            conn.user_id,
            conn.role,
            conn.scope,
            conn.ticket_id,
        )

    async def disconnect(self, conn: ConnectionInfo) -> None:
        async with self._lock:
            self._discard(conn)

        logger.info("ws disconnect user=%s scope=%s ticket=%s", conn.user_id, conn.scope, conn.ticket_id)

    async def disconnect_user(self, user_id: int) -> None:
        """Close every live socket for ``user_id`` (password change, deactivation)."""
        async with self._lock:
            targets: list[ConnectionInfo] = list(self._user_rooms.get(user_id, ()))
            for room in self._ticket_rooms.values():
                for conn in room:
                    if conn.user_id == user_id and conn not in targets:
                        targets.append(conn)
        for conn in targets:
            try:
                await conn.socket.close(code=4401, reason="Session revoked")
            except Exception:
                pass
            await self.disconnect(conn)

    def _discard(self, conn: ConnectionInfo) -> None:
        """Remove a connection from every room. Caller must hold the lock."""
        if conn.ticket_id is not None:
            room = self._ticket_rooms.get(conn.ticket_id)
            if room:
                room.discard(conn)
                if not room:
                    del self._ticket_rooms[conn.ticket_id]

        user_room = self._user_rooms.get(conn.user_id)
        if user_room:
            user_room.discard(conn)
            if not user_room:
                del self._user_rooms[conn.user_id]

        self._staff.discard(conn)
        self._admins.discard(conn)

    # ── broadcast primitives ─────────────────────────────────────────────
    async def broadcast_ticket(
        self,
        ticket_id: int,
        data: Dict[str, Any],
        exclude_socket: Optional[WebSocket] = None,
    ) -> None:
        """Send to the conversation room for one ticket."""
        await self._send_to(list(self._ticket_rooms.get(ticket_id, ())), data, exclude_socket)

    async def broadcast_users(self, user_ids: Iterable[int], data: Dict[str, Any]) -> None:
        """Send to each user's notification stream (deduplicated across rooms)."""
        targets: list[ConnectionInfo] = []
        seen: set[int] = set()
        for user_id in dict.fromkeys(user_ids):
            for conn in self._user_rooms.get(user_id, ()):
                if id(conn) not in seen:
                    seen.add(id(conn))
                    targets.append(conn)
        await self._send_to(targets, data)

    async def broadcast_staff(self, data: Dict[str, Any]) -> None:
        await self._send_to(list(self._staff), data)

    async def broadcast_admins(self, data: Dict[str, Any]) -> None:
        await self._send_to(list(self._admins), data)

    async def broadcast_scoped(
        self,
        *,
        ticket_id: Optional[int],
        user_ids: Iterable[int],
        staff: bool,
        admins: bool,
        notify_data: Dict[str, Any],
        ticket_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Fan one event out, delivering it to each connection exactly once.

        A staff member is usually in both their personal ``user`` room and the
        ``staff`` room, and may additionally have the ticket open. Sending per
        room would duplicate the event, so the target sets are merged here and
        connections in the ticket room are excluded from the notification batch
        (they already received the richer payload).
        """
        ticket_conns: list[ConnectionInfo] = (
            list(self._ticket_rooms.get(ticket_id, ())) if ticket_id is not None else []
        )
        already: set[int] = {id(conn) for conn in ticket_conns}

        others: dict[int, ConnectionInfo] = {}

        def collect(connections: Iterable[ConnectionInfo]) -> None:
            for conn in connections:
                if id(conn) not in already:
                    others[id(conn)] = conn

        for user_id in dict.fromkeys(user_ids):
            collect(self._user_rooms.get(user_id, ()))
        if staff:
            collect(self._staff)
        if admins:
            collect(self._admins)

        if ticket_conns and ticket_data is not None:
            await self._send_to(ticket_conns, ticket_data)
        if others:
            await self._send_to(list(others.values()), notify_data)

    # ── internals ────────────────────────────────────────────────────────
    async def _send_to(
        self,
        connections: list[ConnectionInfo],
        data: Dict[str, Any],
        exclude_socket: Optional[WebSocket] = None,
    ) -> None:
        if not connections:
            return

        is_whisper = data.get("whisper") is True
        text_data = json.dumps(data)
        dead: list[ConnectionInfo] = []

        for conn in connections:
            if exclude_socket is not None and conn.socket is exclude_socket:
                continue
            # Whisper messages are strictly hidden from customers, in every room.
            if is_whisper and not conn.is_staff:
                continue
            try:
                await conn.socket.send_text(text_data)
            except Exception as exc:
                logger.warning("ws send failed user=%s: %s", conn.user_id, exc)
                dead.append(conn)

        # A socket that failed to send is gone; drop it so rooms do not leak.
        if dead:
            async with self._lock:
                for conn in dead:
                    self._discard(conn)

    def connection_count(self) -> int:
        """Total live connections (used by tests and diagnostics)."""
        seen: set[int] = set()
        for room in list(self._ticket_rooms.values()) + list(self._user_rooms.values()):
            for conn in room:
                seen.add(id(conn))
        return len(seen)

    def reset(self) -> None:
        self._ticket_rooms.clear()
        self._user_rooms.clear()
        self._staff.clear()
        self._admins.clear()


hub = WebSocketHub()
