"""End-to-end business flow: bootstrap -> ticket -> staff handling -> CSAT -> analytics."""
import pytest
from litestar.testing import AsyncTestClient

from app.main import app


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


async def register(client: AsyncTestClient, tag: str, password: str = "customerpass123") -> tuple[dict, dict]:
    res = await client.post(
        "/api/auth/register",
        json={
            "email": f"{tag}@test.com",
            "username": f"user_{tag}",
            "full_name": f"User {tag.title()}",
            "password": password,
        },
    )
    assert res.status_code in (200, 201), res.text
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]


@pytest.mark.asyncio
async def test_full_support_lifecycle():
    async with AsyncTestClient(app=app) as client:
        admin_headers = await bootstrap_admin(client)
        customer_headers, customer = await register(client, "alice")

        # Promote a second account to agent through the admin API.
        _, agent_user = await register(client, "bob")
        promoted = await client.patch(
            f"/api/users/{agent_user['id']}/role", json={"role": "agent"}, headers=admin_headers
        )
        assert promoted.status_code == 200
        login = await client.post(
            "/api/auth/login", json={"username_or_email": "user_bob", "password": "customerpass123"}
        )
        agent_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # 1. Customer opens a ticket; the description becomes the first message.
        ticket = (
            await client.post(
                "/api/tickets",
                json={
                    "title": "Payment gateway timeout on checkout",
                    "description": "The payment screen spins forever and then times out.",
                    "priority": "urgent",
                    "category": "billing",
                    "tags": "checkout,payment",
                },
                headers=customer_headers,
            )
        ).json()
        ticket_id = ticket["id"]
        assert ticket["ticket_code"].startswith("TCK-")
        assert ticket["sla_first_response_status"] == "on_track"

        messages = (await client.get(f"/api/tickets/{ticket_id}/messages", headers=customer_headers)).json()
        assert messages["total"] == 1
        assert len(messages["items"]) == 1
        assert messages["items"][0]["sender_role"] == "customer"

        # 2. Agent claims it: assignment moves the ticket to in_progress.
        claimed = await client.patch(
            f"/api/tickets/{ticket_id}/assign", json={"agent_id": agent_user["id"]}, headers=agent_headers
        )
        assert claimed.status_code == 200
        assert claimed.json()["status"] == "in_progress"

        # 3. Agent replies publicly (this satisfies the first-response SLA) ...
        await client.post(
            f"/api/tickets/{ticket_id}/messages",
            json={"content": "Looking into it now."},
            headers=agent_headers,
        )
        after_reply = (await client.get(f"/api/tickets/{ticket_id}", headers=agent_headers)).json()
        assert after_reply["first_responded_at"] is not None
        assert after_reply["sla_first_response_status"] == "fulfilled"
        first_response_due = after_reply["first_response_due_at"]

        # ... and changing priority must not rewrite that historical deadline.
        await client.patch(f"/api/tickets/{ticket_id}/priority", json={"priority": "low"}, headers=agent_headers)
        after_priority = (await client.get(f"/api/tickets/{ticket_id}", headers=agent_headers)).json()
        assert after_priority["first_response_due_at"] == first_response_due

        # 4. Internal note stays hidden from the customer.
        await client.post(
            f"/api/tickets/{ticket_id}/messages",
            json={"content": "Internal: upstream Redis is saturated.", "message_type": "whisper"},
            headers=agent_headers,
        )
        customer_view = (await client.get(f"/api/tickets/{ticket_id}/messages", headers=customer_headers)).json()["items"]
        assert not any(m["message_type"] == "whisper" for m in customer_view)
        agent_view = (await client.get(f"/api/tickets/{ticket_id}/messages", headers=agent_headers)).json()["items"]
        assert any(m["message_type"] == "whisper" for m in agent_view)

        # 5. Resolve, then the customer rates the resolution.
        resolved = await client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "resolved"}, headers=agent_headers
        )
        assert resolved.json()["status"] == "resolved"
        assert resolved.json()["resolved_at"] is not None

        csat = await client.post(
            f"/api/tickets/{ticket_id}/csat",
            json={"score": 5, "comment": "Fast and painless."},
            headers=customer_headers,
        )
        assert csat.status_code in (200, 201)
        assert csat.json()["customer_id"] == customer["id"]

        # 6. Analytics reflects the single resolved, rated ticket.
        summary = (await client.get("/api/analytics/summary", headers=admin_headers)).json()
        assert summary["total_tickets"] == 1
        assert summary["resolved_tickets"] == 1
        assert summary["csat_total_reviews"] == 1
        assert summary["csat_average_score"] == 5.0
        assert summary["sla_compliance_rate"] == 100.0
        assert summary["sla_breached_count"] == 0

        # The agent who handled no CSAT-rated work reports no score rather than 5.0.
        root = next(a for a in summary["agents_performance"] if a["name"] == "Root Admin")
        assert root["csat_avg"] is None


@pytest.mark.asyncio
async def test_unassigning_reopens_the_ticket():
    async with AsyncTestClient(app=app) as client:
        admin_headers = await bootstrap_admin(client)
        customer_headers, _ = await register(client, "carol")
        admin = (await client.get("/api/auth/me", headers=admin_headers)).json()

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Needs an owner", "description": "Nobody owns this yet."},
                headers=customer_headers,
            )
        ).json()

        assigned = await client.patch(
            f"/api/tickets/{ticket['id']}/assign", json={"agent_id": admin["id"]}, headers=admin_headers
        )
        assert assigned.json()["status"] == "in_progress"

        # Dropping the assignee must not leave the ticket stuck in in_progress
        # with nobody responsible for it.
        released = await client.patch(
            f"/api/tickets/{ticket['id']}/assign", json={"agent_id": None}, headers=admin_headers
        )
        assert released.json()["assigned_agent_id"] is None
        assert released.json()["status"] == "open"


@pytest.mark.asyncio
async def test_agents_can_list_assignable_staff_but_not_customers():
    """The reassignment picker needs this route; the full list stays admin-only."""
    async with AsyncTestClient(app=app) as client:
        admin_headers = await bootstrap_admin(client)
        customer_headers, _ = await register(client, "dave")
        _, agent_user = await register(client, "erin")
        await client.patch(
            f"/api/users/{agent_user['id']}/role", json={"role": "agent"}, headers=admin_headers
        )

        # An agent (not an admin) can read the assignable list.
        login = await client.post(
            "/api/auth/login", json={"username_or_email": "user_erin", "password": "customerpass123"}
        )
        agent_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        assignable = await client.get("/api/users/assignable", headers=agent_headers)
        assert assignable.status_code == 200, assignable.text
        roles = {u["role"] for u in assignable.json()}
        assert roles <= {"agent", "admin"}
        assert all(u["is_active"] for u in assignable.json())

        # Customers are excluded from it entirely.
        assert (await client.get("/api/users/assignable", headers=customer_headers)).status_code == 403
        # And the full user list remains administrator-only.
        assert (await client.get("/api/users", headers=agent_headers)).status_code == 403


@pytest.mark.asyncio
async def test_ticket_details_can_be_edited():
    async with AsyncTestClient(app=app) as client:
        admin_headers = await bootstrap_admin(client)
        customer_headers, _ = await register(client, "frank")

        ticket = (
            await client.post(
                "/api/tickets",
                json={
                    "title": "Typo in the title",
                    "description": "The original description body.",
                    "category": "general",
                },
                headers=customer_headers,
            )
        ).json()
        ticket_id = ticket["id"]

        edited = await client.patch(
            f"/api/tickets/{ticket_id}",
            json={
                "title": "Fixed title",
                "description": "The corrected description body.",
                "category": "billing",
                "tags": "billing,invoice",
            },
            headers=customer_headers,
        )
        assert edited.status_code == 200, edited.text
        body = edited.json()
        assert body["title"] == "Fixed title"
        assert body["description"] == "The corrected description body."
        assert body["category"] == "billing"
        assert body["tags"] == "billing,invoice"

        # Status and priority are not editable through this endpoint.
        unchanged = (await client.get(f"/api/tickets/{ticket_id}", headers=admin_headers)).json()
        assert unchanged["status"] == "open"
        assert unchanged["priority"] == "medium"

        # An edit is recorded in the ticket history.
        messages = (await client.get(f"/api/tickets/{ticket_id}/messages", headers=admin_headers)).json()
        assert any("edited" in m["content"].lower() for m in messages["items"])

        # Another customer cannot edit someone else's ticket.
        other_headers, _ = await register(client, "gina")
        assert (
            await client.patch(
                f"/api/tickets/{ticket_id}", json={"title": "Hijacked"}, headers=other_headers
            )
        ).status_code in (403, 404)

        # Invalid values are rejected by validation.
        assert (
            await client.patch(f"/api/tickets/{ticket_id}", json={"title": "x"}, headers=admin_headers)
        ).status_code == 400
