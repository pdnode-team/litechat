"""Persist directed notifications. Staff-wide broadcasts are not stored."""
from __future__ import annotations

from typing import Iterable, Optional

from app.db.session import async_session_factory
from app.models.notification import Notification


def _title_for(event_type: str, notification: dict) -> str:
    code = notification.get("ticket_code") or ""
    mapping = {
        "ticket_created": f"New ticket {code}".strip(),
        "ticket_updated": f"Ticket {code} updated".strip(),
        "message_created": f"New reply on {code}".strip(),
        "csat_submitted": f"CSAT submitted on {code}".strip(),
        "user_updated": "Your account was updated",
        "sla_first_response": f"First-response SLA missed on {code}".strip(),
        "sla_resolution": f"Resolution SLA missed on {code}".strip(),
    }
    return (mapping.get(event_type) or event_type)[:255]


def _body_for(event_type: str, notification: dict) -> str:
    reason = notification.get("reason") or notification.get("title") or ""
    return str(reason)[:2000]


async def persist_for_users(
    user_ids: Iterable[int],
    *,
    event_type: str,
    notification: dict,
    ticket_id: Optional[int] = None,
) -> None:
    unique = sorted({int(user_id) for user_id in user_ids if user_id})
    if not unique:
        return
    title = _title_for(event_type, notification)
    body = _body_for(event_type, notification)
    async with async_session_factory() as session:
        for user_id in unique:
            session.add(
                Notification(
                    user_id=user_id,
                    type=event_type,
                    title=title,
                    body=body,
                    ticket_id=ticket_id,
                )
            )
        await session.commit()
