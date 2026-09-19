"""Central event routing.

Every mutation publishes one :class:`Event`. This module decides where it goes:

* WebSocket — a compact notification to the ``user``/``staff``/``admin`` rooms,
  plus (optionally) the full payload to the ticket conversation room
* Email — handed to :mod:`app.services.notification_service` when the event
  carries an ``email_kind``

Controllers therefore stay free of transport details: they publish, and the
routing policy lives here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services import notification_service
from app.services.websocket_hub import hub

logger = logging.getLogger("litechat.events")

# ── Event types (kept as plain strings so clients can switch on them) ──────
TICKET_CREATED = "ticket_created"
TICKET_UPDATED = "ticket_updated"
MESSAGE_CREATED = "message_created"
CSAT_SUBMITTED = "csat_submitted"
USER_UPDATED = "user_updated"
CATALOG_CHANGED = "catalog_changed"
RATE_LIMITED = "rate_limited"


@dataclass
class Event:
    """One state change and its routing instructions."""

    type: str
    # Compact envelope sent to user/staff/admin rooms.
    notification: Dict[str, Any] = field(default_factory=dict)
    # Full payload for the ticket conversation room, when the client already
    # holds that ticket open and can apply it without refetching.
    ticket_payload: Optional[Dict[str, Any]] = None
    ticket_id: Optional[int] = None
    # Explicit user rooms to notify (the customer, the assignee, ...).
    user_ids: List[int] = field(default_factory=list)
    staff: bool = False
    admins: bool = False
    # Whisper payloads are filtered out for customers by the hub.
    whisper: bool = False
    # Email routing; see notification_service for the policy.
    email_kind: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


async def publish(event: Event) -> None:
    """Fan an event out to WebSockets and, when applicable, to email."""
    message = {"type": event.type, **event.notification}
    if event.whisper:
        message["whisper"] = True

    ticket_data = None
    if event.ticket_id is not None and event.ticket_payload is not None:
        ticket_data = {**event.ticket_payload}
        if event.whisper:
            ticket_data["whisper"] = True

    await hub.broadcast_scoped(
        ticket_id=event.ticket_id,
        user_ids=event.user_ids,
        staff=event.staff,
        admins=event.admins,
        notify_data=message,
        ticket_data=ticket_data,
    )

    if event.email_kind:
        await notification_service.handle(event.email_kind, event.context)


async def publish_catalog_change(
    resource: str,
    action: str,
    *,
    entity_id: Optional[int] = None,
    actor_name: str = "Someone",
) -> None:
    """A managed app / ticket type / FAQ article / canned response changed.

    Staff lists and the admin console reload the affected tab without polling.
    """
    await publish(
        Event(
            type=CATALOG_CHANGED,
            notification={
                "resource": resource,
                "action": action,
                "entity_id": entity_id,
                "actor_name": actor_name,
            },
            staff=True,
            admins=True,
        )
    )


async def publish_user_change(
    user_id: int,
    action: str,
    *,
    actor_name: str = "Someone",
    actor_user_id: Optional[int] = None,
) -> None:
    """A user's role or activation state changed.

    The affected user is notified directly so their own session can refresh its
    permissions; admins see the change so the user table stays current.
    """
    await publish(
        Event(
            type=USER_UPDATED,
            notification={
                "user_id": user_id,
                "action": action,
                "actor_name": actor_name,
            },
            user_ids=[user_id],
            admins=True,
            context={"actor_user_id": actor_user_id},
        )
    )
