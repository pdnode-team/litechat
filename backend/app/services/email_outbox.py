"""Persist-then-send outbound mail.

The HTTP request only inserts a row. A background loop (and an immediate
kick after enqueue) claims due rows and hands them to SMTP. Claiming uses an
optimistic ``pending -> in_flight`` update so two workers racing the same row
send it at most once in the common case. SQLite has no ``FOR UPDATE SKIP LOCKED``,
so running more than one replica can still double-send under contention —
keep replicas at 1, or accept that risk.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import select, update

from app.config import EMAIL_OUTBOX_MAX_ATTEMPTS, EMAIL_OUTBOX_WORKER
from app.db.base import utcnow
from app.db.session import async_session_factory
from app.models.email_outbox import (
    STATUS_FAILED,
    STATUS_IN_FLIGHT,
    STATUS_PENDING,
    STATUS_SENT,
    EmailOutbox,
)

logger = logging.getLogger("litechat.outbox")

_BATCH = 20
_INTERVAL_SECONDS = 60
_STUCK_AFTER = timedelta(minutes=10)


def _backoff(attempts: int):
    """Wait 1, 2, 4, 8, … minutes after successive failures."""
    minutes = 2 ** max(attempts - 1, 0)
    return utcnow() + timedelta(minutes=minutes)


def _clip_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return text if len(text) <= 2000 else text[:1997] + "..."


async def enqueue(to: str, subject: str, body: str, kind: str = "transactional") -> Optional[int]:
    if not to:
        return None
    async with async_session_factory() as session:
        row = EmailOutbox(
            to_address=to[:255],
            subject=subject[:255],
            body=body,
            kind=(kind or "transactional")[:50],
            status=STATUS_PENDING,
            attempts=0,
            next_attempt_at=utcnow(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        row_id = row.id
    if EMAIL_OUTBOX_WORKER:
        try:
            asyncio.get_running_loop().create_task(process_due_outbox())
        except RuntimeError:
            pass
    return row_id


async def process_due_outbox(limit: int = _BATCH) -> int:
    """Claim and deliver due rows. Returns how many were attempted."""
    from app.services.email_service import deliver_email

    now = utcnow()
    processed = 0
    async with async_session_factory() as session:
        stuck_before = now - _STUCK_AFTER
        await session.execute(
            update(EmailOutbox)
            .where(
                EmailOutbox.status == STATUS_IN_FLIGHT,
                EmailOutbox.updated_at < stuck_before,
            )
            .values(status=STATUS_PENDING, next_attempt_at=now, updated_at=now)
        )
        await session.commit()

        stmt = (
            select(EmailOutbox.id)
            .where(
                EmailOutbox.status == STATUS_PENDING,
                EmailOutbox.next_attempt_at <= now,
            )
            .order_by(EmailOutbox.id)
            .limit(limit)
        )
        from app.db.session import engine as db_engine

        if db_engine.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        due_ids = list((await session.execute(stmt)).scalars().all())

    for row_id in due_ids:
        async with async_session_factory() as session:
            claimed = await session.execute(
                update(EmailOutbox)
                .where(
                    EmailOutbox.id == row_id,
                    EmailOutbox.status == STATUS_PENDING,
                )
                .values(status=STATUS_IN_FLIGHT, updated_at=utcnow())
            )
            await session.commit()
            if claimed.rowcount != 1:
                continue
            row = await session.get(EmailOutbox, row_id)
            if row is None:
                continue
            to_address, subject, body = row.to_address, row.subject, row.body

        error: Optional[str] = None
        sent = False
        try:
            sent = await deliver_email(to_address, subject, body)
            if not sent:
                error = "SMTP did not accept the message (disabled, unconfigured, or rejected)."
        except Exception as exc:
            logger.exception("Outbox delivery failed for id=%s to=%s", row_id, to_address)
            error = _clip_error(exc)

        async with async_session_factory() as session:
            row = await session.get(EmailOutbox, row_id)
            if row is None:
                continue
            now = utcnow()
            if sent:
                row.status = STATUS_SENT
                row.last_error = None
                row.updated_at = now
            else:
                row.attempts = (row.attempts or 0) + 1
                row.last_error = error
                row.updated_at = now
                if row.attempts >= EMAIL_OUTBOX_MAX_ATTEMPTS:
                    row.status = STATUS_FAILED
                else:
                    row.status = STATUS_PENDING
                    row.next_attempt_at = _backoff(row.attempts)
            await session.commit()
        processed += 1
    return processed


async def worker_loop() -> None:
    while True:
        try:
            await process_due_outbox()
        except Exception:
            logger.exception("Email outbox worker iteration failed")
        await asyncio.sleep(_INTERVAL_SECONDS)
