"""Persist-then-send mail: enqueue, retry, give up."""
import pytest
from litestar.testing import AsyncTestClient
from sqlalchemy import select

from app.db.session import async_session_factory
from app.main import app
from app.models.email_outbox import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
    EmailOutbox,
)
from app.services import email_outbox, email_service, settings_service


@pytest.fixture(autouse=True)
def reset_settings():
    settings_service.invalidate()
    yield
    settings_service.invalidate()


async def _row_for(to: str) -> EmailOutbox:
    async with async_session_factory() as session:
        return (
            await session.execute(select(EmailOutbox).where(EmailOutbox.to_address == to))
        ).scalar_one()


@pytest.mark.asyncio
async def test_send_email_enqueues_instead_of_talking_to_smtp(monkeypatch):
    called = []

    async def boom(*args, **kwargs):
        called.append(args)
        raise AssertionError("SMTP must not run on the request path")

    monkeypatch.setattr(email_service, "deliver_email", boom)

    assert await email_service.send_email("queue@formtest.com", "Hello", "Body", kind="test")
    assert called == []
    row = await _row_for("queue@formtest.com")
    assert row.status == STATUS_PENDING
    assert row.kind == "test"
    assert row.body == "Body"


@pytest.mark.asyncio
async def test_outbox_retry_succeeds_on_a_later_attempt(monkeypatch):
    attempts = {"n": 0}

    async def flaky(to, subject, body):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("smtp timeout")
        return True

    monkeypatch.setattr(email_service, "deliver_email", flaky)
    await email_service.send_email("retry@formtest.com", "Hi", "x")

    assert await email_outbox.process_due_outbox() == 1
    row = await _row_for("retry@formtest.com")
    assert row.status == STATUS_PENDING
    assert row.attempts == 1
    assert "smtp timeout" in (row.last_error or "")

    row.next_attempt_at = row.created_at
    async with async_session_factory() as session:
        stored = await session.get(EmailOutbox, row.id)
        stored.next_attempt_at = stored.created_at
        stored.status = STATUS_PENDING
        await session.commit()

    assert await email_outbox.process_due_outbox() == 1
    row = await _row_for("retry@formtest.com")
    assert row.status == STATUS_SENT
    assert row.last_error is None


@pytest.mark.asyncio
async def test_outbox_marks_failed_after_max_attempts(monkeypatch):
    async def always_down(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(email_service, "deliver_email", always_down)
    monkeypatch.setattr(email_outbox, "EMAIL_OUTBOX_MAX_ATTEMPTS", 2)
    monkeypatch.setattr("app.services.email_outbox.EMAIL_OUTBOX_MAX_ATTEMPTS", 2)

    await email_service.send_email("giveup@formtest.com", "Hi", "x")
    assert await email_outbox.process_due_outbox() == 1
    row = await _row_for("giveup@formtest.com")
    assert row.status == STATUS_PENDING

    async with async_session_factory() as session:
        stored = await session.get(EmailOutbox, row.id)
        stored.next_attempt_at = stored.created_at
        await session.commit()

    assert await email_outbox.process_due_outbox() == 1
    row = await _row_for("giveup@formtest.com")
    assert row.status == STATUS_FAILED
    assert row.attempts == 2
    assert "connection refused" in (row.last_error or "")


@pytest.mark.asyncio
async def test_ticket_create_succeeds_when_smtp_raises(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(email_service, "deliver_email", boom)
    await settings_service.set_many(
        {"smtp_enabled": True, "smtp_host": "smtp.formtest.com", "support_email": ""}
    )

    async with AsyncTestClient(app=app) as client:
        admin = await client.post(
            "/api/auth/setup-admin",
            json={
                "email": "admin@formtest.com",
                "username": "root_admin",
                "full_name": "Root Admin",
                "password": "rootpass123",
            },
        )
        assert admin.status_code in (200, 201), admin.text
        customer = await client.post(
            "/api/auth/register",
            json={
                "email": "cust@formtest.com",
                "username": "cust_user",
                "full_name": "Cust User",
                "password": "customerpass123",
            },
        )
        headers = {"Authorization": f"Bearer {customer.json()['access_token']}"}
        created = await client.post(
            "/api/tickets",
            json={
                "title": "Need help",
                "description": "Something broke in checkout.",
                "category": "technical",
                "priority": "medium",
            },
            headers=headers,
        )
        assert created.status_code in (200, 201), created.text

    async with async_session_factory() as session:
        rows = (await session.execute(select(EmailOutbox))).scalars().all()
    assert rows
    assert all(row.status == STATUS_PENDING for row in rows)

    await email_outbox.process_due_outbox()
    async with async_session_factory() as session:
        rows = (await session.execute(select(EmailOutbox))).scalars().all()
    assert rows
    assert all(row.attempts >= 1 for row in rows)


@pytest.mark.asyncio
async def test_admin_can_list_failed_outbox_rows(monkeypatch):
    async def always_down(*args, **kwargs):
        raise RuntimeError("no route to host")

    monkeypatch.setattr(email_service, "deliver_email", always_down)
    monkeypatch.setattr("app.services.email_outbox.EMAIL_OUTBOX_MAX_ATTEMPTS", 1)

    await email_service.send_email("ops@formtest.com", "Failed subject", "body")
    await email_outbox.process_due_outbox()

    async with AsyncTestClient(app=app) as client:
        admin = await client.post(
            "/api/auth/setup-admin",
            json={
                "email": "admin@formtest.com",
                "username": "root_admin",
                "full_name": "Root Admin",
                "password": "rootpass123",
            },
        )
        headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
        res = await client.get("/api/settings/email/outbox", headers=headers)
        assert res.status_code == 200, res.text
        items = res.json()
        assert items
        assert items[0]["to_address"] == "ops@formtest.com"
        assert items[0]["status"] == STATUS_FAILED
        assert "no route to host" in items[0]["last_error"]

        customer = await client.post(
            "/api/auth/register",
            json={
                "email": "cust@formtest.com",
                "username": "cust_user",
                "full_name": "Cust User",
                "password": "customerpass123",
            },
        )
        forbidden = await client.get(
            "/api/settings/email/outbox",
            headers={"Authorization": f"Bearer {customer.json()['access_token']}"},
        )
        assert forbidden.status_code == 403
