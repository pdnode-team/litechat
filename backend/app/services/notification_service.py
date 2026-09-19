"""Who gets an email, for which event.

Kept separate from ``events.py`` so the routing policy is readable in one place:

* a new ticket            -> every active staff member (+ the support inbox)
* a public staff reply    -> the customer who owns the ticket
* a customer reply        -> the assigned agent, or every staff member if unassigned
* assignment              -> the new assignee
* resolved / closed       -> the customer
* internal notes (whisper) -> nobody, ever
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.user import User
from app.services import email_service, settings_service

logger = logging.getLogger("litechat.notifications")

KIND_NEW_TICKET = "new_ticket"
KIND_STAFF_REPLY = "staff_reply"
KIND_CUSTOMER_REPLY = "customer_reply"
KIND_ASSIGNED = "assigned"
KIND_RESOLVED = "resolved"


def _dedupe(addresses: Iterable[Optional[str]], exclude: Iterable[Optional[str]] = ()) -> List[str]:
    excluded = {address.lower() for address in exclude if address}
    seen: set[str] = set()
    result: List[str] = []
    for address in addresses:
        if not address:
            continue
        lowered = address.lower()
        if lowered in excluded or lowered in seen:
            continue
        seen.add(lowered)
        result.append(address)
    return result


async def _staff_emails() -> List[str]:
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(User).where(
                    User.role.in_(("agent", "admin")),
                    User.is_active.is_(True),
                )
            )
        ).scalars().all()
        return [user.email for user in rows]


async def _user_email(user_id: Optional[int]) -> Optional[str]:
    if not user_id:
        return None
    async with async_session_factory() as session:
        user = await session.get(User, user_id)
        return user.email if user and user.is_active else None


def _excerpt(text: str, limit: int = 400) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned if len(cleaned) <= limit else f"{cleaned[:limit]}..."


async def handle(kind: str, context: Dict[str, Any]) -> None:
    """Send the emails for one event. Never raises to the caller."""
    try:
        config = await settings_service.get_all()
        await _dispatch(kind, context, config)
    except Exception:
        # A mail problem must never break the API call that triggered it.
        logger.exception("Notification dispatch failed for %s", kind)


async def _dispatch(kind: str, context: Dict[str, Any], config: Dict[str, Any]) -> None:
    if not config.get("smtp_enabled"):
        return

    ticket_id = context.get("ticket_id")
    if ticket_id is None:
        return

    code = context.get("ticket_code") or f"#{ticket_id}"
    title = context.get("title") or "(no title)"
    actor_name = context.get("actor_name") or "Someone"
    actor_email = context.get("actor_email")
    excerpt = _excerpt(context.get("message_excerpt") or "")
    support_email = config.get("support_email") or ""

    if kind == KIND_NEW_TICKET:
        if not config.get("notify_new_ticket"):
            return
        recipients = _dedupe([*await _staff_emails(), support_email], exclude=[actor_email])
        await email_service.send_ticket_notification(
            recipients,
            f"[LiteChat] New ticket {code}: {title}",
            f"A new ticket was opened by {actor_name}.",
            [
                f"Ticket:    {code}",
                f"Title:     {title}",
                f"Priority:  {context.get('priority', 'medium')}",
                f"Category:  {context.get('category', 'general')}",
                "",
                "First message:",
                excerpt,
            ],
            ticket_id,
            action_label="Claim it",
        )
        return

    if kind == KIND_STAFF_REPLY:
        if not config.get("notify_ticket_reply"):
            return
        recipient = await _user_email(context.get("customer_id"))
        await email_service.send_ticket_notification(
            _dedupe([recipient], exclude=[actor_email]),
            f"[LiteChat] Reply on {code}: {title}",
            f"{actor_name} replied to your ticket.",
            [f"Ticket: {code}", "", "Message:", excerpt],
            ticket_id,
            action_label="View and reply",
        )
        return

    if kind == KIND_CUSTOMER_REPLY:
        if not config.get("notify_ticket_reply"):
            return
        assigned = await _user_email(context.get("assigned_agent_id"))
        recipients = _dedupe(
            [assigned] if assigned else [*await _staff_emails(), support_email],
            exclude=[actor_email],
        )
        await email_service.send_ticket_notification(
            recipients,
            f"[LiteChat] Customer replied on {code}: {title}",
            f"{actor_name} replied to ticket {code}.",
            [f"Ticket: {code}", "", "Message:", excerpt],
            ticket_id,
            action_label="Open the ticket",
        )
        return

    if kind == KIND_ASSIGNED:
        if not config.get("notify_assignment"):
            return
        recipients = _dedupe([await _user_email(context.get("assigned_agent_id"))], exclude=[actor_email])
        await email_service.send_ticket_notification(
            recipients,
            f"[LiteChat] Ticket {code} assigned to you",
            f"{actor_name} assigned {code} to you.",
            [f"Ticket: {code}", f"Title:  {title}"],
            ticket_id,
            action_label="Open the ticket",
        )
        return

    if kind == KIND_RESOLVED:
        if not config.get("notify_status_change"):
            return
        recipient = await _user_email(context.get("customer_id"))
        await email_service.send_ticket_notification(
            _dedupe([recipient], exclude=[actor_email]),
            f"[LiteChat] Ticket {code} is {context.get('status', 'resolved')}",
            f"Ticket {code} was marked {context.get('status', 'resolved')} by {actor_name}.",
            [
                f"Ticket: {code}",
                f"Title:  {title}",
                "",
                "If the issue is not solved, reply to reopen the ticket.",
            ],
            ticket_id,
            action_label="View the ticket",
        )
        return

    logger.debug("No email policy for event kind %s", kind)
