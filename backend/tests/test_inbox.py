"""Persisted inbox notifications and SLA-due alerts."""
from datetime import timedelta

import pytest
from litestar.testing import AsyncTestClient
from sqlalchemy import select

from app.db.base import utcnow
from app.db.session import async_session_factory
from app.main import app
from app.models.notification import Notification
from app.models.ticket import Ticket
from app.services import sla_watch


async def _register(client: AsyncTestClient, tag: str) -> tuple[dict, dict]:
    res = await client.post(
        "/api/auth/register",
        json={
            "email": f"{tag}@formtest.com",
            "username": f"user_{tag}",
            "full_name": f"User {tag.title()}",
            "password": "customerpass123",
        },
    )
    assert res.status_code in (200, 201), res.text
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]


@pytest.mark.asyncio
async def test_directed_events_are_persisted_and_survive_a_refetch():
    async with AsyncTestClient(app=app) as client:
        customer_headers, customer = await _register(client, "inbox")
        created = await client.post(
            "/api/tickets",
            json={"title": "Inbox ticket", "description": "Please persist this."},
            headers=customer_headers,
        )
        assert created.status_code in (200, 201), created.text

        listed = await client.get("/api/notifications", headers=customer_headers)
        assert listed.status_code == 200, listed.text
        items = listed.json()["items"]
        assert items
        assert items[0]["ticket_id"] == created.json()["id"]
        assert items[0]["read_at"] is None

        marked = await client.post(
            "/api/notifications/read",
            json={"ids": [items[0]["id"]]},
            headers=customer_headers,
        )
        assert marked.json()["updated"] == 1
        reread = await client.get("/api/notifications", headers=customer_headers)
        assert reread.json()["items"][0]["read_at"]


@pytest.mark.asyncio
async def test_mark_all_read_and_pagination_unread_first():
    async with AsyncTestClient(app=app) as client:
        headers, _ = await _register(client, "pager")
        await client.post(
            "/api/tickets",
            json={"title": "First note", "description": "Need help now."},
            headers=headers,
        )
        await client.post(
            "/api/tickets",
            json={"title": "Second note", "description": "Still need help."},
            headers=headers,
        )
        page = await client.get("/api/notifications", headers=headers, params={"limit": 1, "offset": 0})
        assert page.json()["total"] >= 2
        assert len(page.json()["items"]) == 1
        await client.post("/api/notifications/read", json={"all": True}, headers=headers)
        after = await client.get("/api/notifications", headers=headers)
        assert all(item["read_at"] for item in after.json()["items"])


@pytest.mark.asyncio
async def test_sla_watch_alerts_once():
    async with AsyncTestClient(app=app) as client:
        admin = await client.post(
            "/api/auth/setup-admin",
            json={
                "email": "sla-admin@formtest.com",
                "username": "sla_admin",
                "full_name": "SLA Admin",
                "password": "rootpass123",
            },
        )
        assert admin.status_code in (200, 201), admin.text
        headers, user = await _register(client, "slawatch")
        created = await client.post(
            "/api/tickets",
            json={"title": "Overdue", "description": "This will miss SLA.", "priority": "urgent"},
            headers=headers,
        )
        ticket_id = created.json()["id"]

        async with async_session_factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            ticket.first_response_due_at = utcnow() - timedelta(minutes=5)
            ticket.sla_first_alerted_at = None
            await session.commit()

        assert await sla_watch.scan_sla_breaches() >= 1
        assert await sla_watch.scan_sla_breaches() == 0

        async with async_session_factory() as session:
            rows = (
                await session.execute(select(Notification).where(Notification.ticket_id == ticket_id))
            ).scalars().all()
        sla_rows = [row for row in rows if row.type == "sla_first_response"]
        assert len(sla_rows) == 1
