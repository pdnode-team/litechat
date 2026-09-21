"""Ticket list filters: tag, type, app, dates, and message-body search."""
import pytest
from litestar.testing import AsyncTestClient

from app.main import app


async def _customer(client: AsyncTestClient, tag: str) -> dict:
    res = await client.post(
        "/api/auth/register",
        json={
            "email": f"{tag}@formtest.com",
            "username": f"user_{tag}",
            "full_name": f"User {tag.title()}",
            "password": "customerpass123",
        },
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.mark.asyncio
async def test_tag_filter_matches_comma_separated_items_not_substrings():
    async with AsyncTestClient(app=app) as client:
        headers = await _customer(client, "tags")
        await client.post(
            "/api/tickets",
            json={"title": "Hardware disk", "description": "Disk failed.", "tags": "hardware, urgent"},
            headers=headers,
        )
        await client.post(
            "/api/tickets",
            json={"title": "Other", "description": "Not hardware.", "tags": "hardware-failure"},
            headers=headers,
        )
        hit = await client.get("/api/tickets", params={"tag": "hardware"}, headers=headers)
        assert hit.status_code == 200
        titles = [item["title"] for item in hit.json()["items"]]
        assert titles == ["Hardware disk"]
        assert hit.json()["total"] == 1

        wild = await client.get("/api/tickets", params={"tag": "%"}, headers=headers)
        assert wild.json()["total"] == 0


@pytest.mark.asyncio
async def test_search_includes_message_bodies_and_escapes_wildcards():
    async with AsyncTestClient(app=app) as client:
        headers = await _customer(client, "msgs")
        first = await client.post(
            "/api/tickets",
            json={"title": "Silent title", "description": "No keyword here."},
            headers=headers,
        )
        ticket_id = first.json()["id"]
        await client.post(
            f"/api/tickets/{ticket_id}/messages",
            json={"content": "the zebra protocol failed"},
            headers=headers,
        )
        await client.post(
            "/api/tickets",
            json={"title": "Unrelated", "description": "Nothing to see."},
            headers=headers,
        )

        found = await client.get("/api/tickets", params={"search": "zebra"}, headers=headers)
        assert found.json()["total"] == 1
        assert found.json()["items"][0]["id"] == ticket_id

        percent = await client.get("/api/tickets", params={"search": "%"}, headers=headers)
        assert percent.json()["total"] == 0


@pytest.mark.asyncio
async def test_date_and_type_filters():
    async with AsyncTestClient(app=app) as client:
        headers = await _customer(client, "dates")
        created = await client.post(
            "/api/tickets",
            json={"title": "Dated ticket", "description": "Created today."},
            headers=headers,
        )
        assert created.status_code in (200, 201)
        today = created.json()["created_at"][:10]
        in_range = await client.get(
            "/api/tickets",
            params={"created_from": today, "created_to": today},
            headers=headers,
        )
        assert in_range.json()["total"] == 1
        empty = await client.get(
            "/api/tickets",
            params={"created_from": "1999-01-01", "created_to": "1999-01-02"},
            headers=headers,
        )
        assert empty.json()["total"] == 0
        missing_type = await client.get("/api/tickets", params={"ticket_type_id": 999999}, headers=headers)
        assert missing_type.json()["total"] == 0
        missing_app = await client.get("/api/tickets", params={"app_id": 999999}, headers=headers)
        assert missing_app.json()["total"] == 0
