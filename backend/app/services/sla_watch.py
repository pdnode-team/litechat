"""Alert once when an SLA deadline passes."""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import or_, select

from app.db.base import utcnow
from app.db.session import async_session_factory
from app.models.ticket import Ticket
from app.models.user import User
from app.services import events as event_bus
from app.services.events import Event

logger = logging.getLogger("litechat.sla")
_INTERVAL = 60


async def _staff_ids() -> list[int]:
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(User.id).where(User.role.in_(("agent", "admin")), User.is_active.is_(True))
            )
        ).scalars().all()
        return list(rows)


async def scan_sla_breaches() -> int:
    """Stamp and notify each overdue ticket at most once per deadline. Returns alerts sent."""
    now = utcnow()
    sent = 0
    async with async_session_factory() as session:
        tickets = (
            await session.execute(
                select(Ticket).where(
                    or_(
                        (Ticket.first_response_due_at <= now)
                        & Ticket.first_responded_at.is_(None)
                        & Ticket.sla_first_alerted_at.is_(None),
                        (Ticket.resolution_due_at <= now)
                        & Ticket.resolved_at.is_(None)
                        & Ticket.sla_resolution_alerted_at.is_(None)
                        & Ticket.status.notin_(("resolved", "closed")),
                    )
                )
            )
        ).scalars().all()
        snapshot = [
            (
                t.id,
                t.ticket_code,
                t.title,
                t.assigned_agent_id,
                t.first_response_due_at,
                t.first_responded_at,
                t.sla_first_alerted_at,
                t.resolution_due_at,
                t.resolved_at,
                t.sla_resolution_alerted_at,
                t.status,
            )
            for t in tickets
        ]

    staff_ids = await _staff_ids()
    for (
        ticket_id,
        code,
        title,
        assigned,
        first_due,
        first_done,
        first_alerted,
        res_due,
        resolved,
        res_alerted,
        status,
    ) in snapshot:
        recipients = [assigned] if assigned else staff_ids
        if first_due and first_due <= now and first_done is None and first_alerted is None:
            async with async_session_factory() as session:
                row = await session.get(Ticket, ticket_id)
                if row and row.sla_first_alerted_at is None and row.first_responded_at is None:
                    row.sla_first_alerted_at = now
                    await session.commit()
                    await event_bus.publish(
                        Event(
                            type="sla_first_response",
                            notification={
                                "ticket_id": ticket_id,
                                "ticket_code": code,
                                "title": title,
                                "reason": "first_response_due",
                            },
                            ticket_id=ticket_id,
                            user_ids=[uid for uid in recipients if uid],
                        )
                    )
                    sent += 1
        if (
            res_due
            and res_due <= now
            and resolved is None
            and res_alerted is None
            and status not in ("resolved", "closed")
        ):
            async with async_session_factory() as session:
                row = await session.get(Ticket, ticket_id)
                if row and row.sla_resolution_alerted_at is None and row.resolved_at is None:
                    row.sla_resolution_alerted_at = now
                    await session.commit()
                    await event_bus.publish(
                        Event(
                            type="sla_resolution",
                            notification={
                                "ticket_id": ticket_id,
                                "ticket_code": code,
                                "title": title,
                                "reason": "resolution_due",
                            },
                            ticket_id=ticket_id,
                            user_ids=[uid for uid in recipients if uid],
                        )
                    )
                    sent += 1
    return sent


async def worker_loop() -> None:
    while True:
        try:
            await scan_sla_breaches()
        except Exception:
            logger.exception("SLA watch iteration failed")
        await asyncio.sleep(_INTERVAL)
