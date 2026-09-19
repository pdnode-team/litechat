"""Pagination envelope, bounds and chat-page ordering."""
import pytest
from litestar.testing import AsyncTestClient

from app.main import app
from app.schemas.pagination import MAX_PAGE_SIZE


async def bootstrap_admin(client: AsyncTestClient) -> dict:
    res = await client.post(
        "/api/auth/setup-admin",
        json={
            "email": "root@test.com",
            "username": "root_admin",
            "full_name": "Root Admin",
            "password": "rootpass123",
        },
    )
    assert res.status_code in (200, 201), res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def register_customer(client: AsyncTestClient, tag: str) -> dict:
    res = await client.post(
        "/api/auth/register",
        json={
            "email": f"{tag}@test.com",
            "username": f"user_{tag}",
            "full_name": f"User {tag.title()}",
            "password": "customerpass123",
        },
    )
    assert res.status_code in (200, 201), res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def create_tickets(client: AsyncTestClient, headers: dict, count: int) -> list[dict]:
    created = []
    for index in range(count):
        res = await client.post(
            "/api/tickets",
            json={"title": f"Ticket number {index}", "description": f"Body for ticket {index}"},
            headers=headers,
        )
        assert res.status_code in (200, 201), res.text
        created.append(res.json())
    return created


@pytest.mark.asyncio
async def test_ticket_list_is_paginated():
    async with AsyncTestClient(app=app) as client:
        admin = await bootstrap_admin(client)
        customer = await register_customer(client, "pager")
        await create_tickets(client, customer, 5)

        page = (await client.get("/api/tickets", headers=admin)).json()
        assert set(page) >= {"items", "total", "limit", "offset"}
        assert page["total"] == 5
        assert page["offset"] == 0
        assert len(page["items"]) == 5

        first = (await client.get("/api/tickets?limit=2&offset=0", headers=admin)).json()
        assert len(first["items"]) == 2
        assert first["total"] == 5

        second = (await client.get("/api/tickets?limit=2&offset=2", headers=admin)).json()
        assert len(second["items"]) == 2

        last = (await client.get("/api/tickets?limit=2&offset=4", headers=admin)).json()
        assert len(last["items"]) == 1

        # Pages must not overlap and must together cover every ticket.
        ids = [t["id"] for t in first["items"] + second["items"] + last["items"]]
        assert len(ids) == len(set(ids)) == 5

        # Newest first.
        assert first["items"][0]["id"] > first["items"][1]["id"]


@pytest.mark.asyncio
async def test_pagination_bounds_are_validated():
    async with AsyncTestClient(app=app) as client:
        admin = await bootstrap_admin(client)

        assert (await client.get("/api/tickets?limit=0", headers=admin)).status_code == 400
        assert (await client.get("/api/tickets?limit=-5", headers=admin)).status_code == 400
        assert (await client.get(f"/api/tickets?limit={MAX_PAGE_SIZE + 1}", headers=admin)).status_code == 400
        assert (await client.get("/api/tickets?offset=-1", headers=admin)).status_code == 400

        at_max = await client.get(f"/api/tickets?limit={MAX_PAGE_SIZE}", headers=admin)
        assert at_max.status_code == 200
        assert at_max.json()["limit"] == MAX_PAGE_SIZE


@pytest.mark.asyncio
async def test_all_list_endpoints_share_the_envelope():
    async with AsyncTestClient(app=app) as client:
        admin = await bootstrap_admin(client)
        for path in ["/api/tickets", "/api/users", "/api/apps", "/api/ticket-types", "/api/faq", "/api/canned-responses"]:
            body = (await client.get(path, headers=admin)).json()
            assert isinstance(body, dict), f"{path} did not return a page envelope"
            assert set(body) >= {"items", "total", "limit", "offset"}, path


@pytest.mark.asyncio
async def test_messages_page_zero_holds_the_newest_messages_in_order():
    async with AsyncTestClient(app=app) as client:
        admin = await bootstrap_admin(client)
        customer = await register_customer(client, "chatter")

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Chat ordering", "description": "Initial description body"},
                headers=customer,
            )
        ).json()
        ticket_id = ticket["id"]

        for index in range(4):
            res = await client.post(
                f"/api/tickets/{ticket_id}/messages",
                json={"content": f"follow-up {index}"},
                headers=customer,
            )
            assert res.status_code in (200, 201), res.text

        # 5 messages total (the initial description plus 4 follow-ups).
        page0 = (await client.get(f"/api/tickets/{ticket_id}/messages?limit=2", headers=admin)).json()
        assert page0["total"] == 5
        assert len(page0["items"]) == 2
        contents = [m["content"] for m in page0["items"]]
        # Newest slice, but returned chronologically so it can be rendered as-is.
        assert contents == ["follow-up 2", "follow-up 3"]

        page1 = (
            await client.get(f"/api/tickets/{ticket_id}/messages?limit=2&offset=2", headers=admin)
        ).json()
        assert [m["content"] for m in page1["items"]] == ["follow-up 0", "follow-up 1"]

        page2 = (
            await client.get(f"/api/tickets/{ticket_id}/messages?limit=2&offset=4", headers=admin)
        ).json()
        assert [m["content"] for m in page2["items"]] == ["Initial description body"]


@pytest.mark.asyncio
async def test_upload_accepts_multipart_after_annotation_change():
    async with AsyncTestClient(app=app) as client:
        await bootstrap_admin(client)
        customer = await register_customer(client, "uploader")

        res = await client.post(
            "/api/upload",
            files={"data": ("note.txt", b"hello multipart", "text/plain")},
            headers=customer,
        )
        assert res.status_code in (200, 201), res.text
        body = res.json()
        assert body["name"] == "note.txt"
        assert body["size"] == len(b"hello multipart")

        from app.config import UPLOAD_DIR

        stored = (UPLOAD_DIR / body["url"].rsplit("/", 1)[-1]).resolve()
        try:
            assert stored.exists()
        finally:
            stored.unlink(missing_ok=True)
