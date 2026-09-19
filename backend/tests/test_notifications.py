"""Email notification policy: who gets told about what."""
import pytest
from litestar.testing import AsyncTestClient

from app.main import app
from app.services import email_service, settings_service

SENT: list[dict] = []


@pytest.fixture(autouse=True)
def capture_mail(monkeypatch):
    """Capture ticket notification emails instead of opening an SMTP connection."""
    SENT.clear()

    async def fake_send(recipients, subject, heading, lines, ticket_id, action_label=None):
        SENT.append(
            {
                "recipients": list(recipients),
                "subject": subject,
                "heading": heading,
                "lines": lines,
                "ticket_id": ticket_id,
            }
        )

    monkeypatch.setattr(email_service, "send_ticket_notification", fake_send)


@pytest.fixture(autouse=True)
def enable_email():
    settings_service.invalidate()
    yield
    settings_service.invalidate()


async def enable_outbound_email(enabled: bool = True) -> None:
    await settings_service.set_many(
        {
            "smtp_enabled": enabled,
            "smtp_host": "smtp.test" if enabled else "",
            "support_email": "",
        }
    )


async def bootstrap(client: AsyncTestClient) -> dict:
    res = await client.post(
        "/api/auth/setup-admin",
        json={
            "email": "admin@test.com",
            "username": "root_admin",
            "full_name": "Root Admin",
            "password": "rootpass123",
        },
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def register(client: AsyncTestClient, tag: str) -> tuple[dict, dict]:
    res = await client.post(
        "/api/auth/register",
        json={
            "email": f"{tag}@test.com",
            "username": f"user_{tag}",
            "full_name": f"User {tag.title()}",
            "password": "customerpass123",
        },
    )
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]


def recipients_of(index: int = 0) -> list[str]:
    return SENT[index]["recipients"]


@pytest.mark.asyncio
async def test_new_ticket_emails_every_staff_member():
    async with AsyncTestClient(app=app) as client:
        admin_headers = await bootstrap(client)
        _, agent_user = await register(client, "erin")
        await client.patch(
            f"/api/users/{agent_user['id']}/role", json={"role": "agent"}, headers=admin_headers
        )
        customer_headers, _ = await register(client, "cust")
        await enable_outbound_email()

        await client.post(
            "/api/tickets",
            json={"title": "Printer on fire", "description": "It is really on fire."},
            headers=customer_headers,
        )

    assert len(SENT) == 1
    assert "New ticket" in SENT[0]["subject"]
    # Both staff accounts, and not the customer who opened it.
    assert sorted(recipients_of()) == ["admin@test.com", "erin@test.com"]


@pytest.mark.asyncio
async def test_staff_reply_emails_the_customer():
    async with AsyncTestClient(app=app) as client:
        admin_headers = await bootstrap(client)
        customer_headers, _ = await register(client, "cust")
        await enable_outbound_email()

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Where is my invoice", "description": "Please send the invoice."},
                headers=customer_headers,
            )
        ).json()
        SENT.clear()

        await client.post(
            f"/api/tickets/{ticket['id']}/messages",
            json={"content": "It is attached to your account."},
            headers=admin_headers,
        )

    assert len(SENT) == 1
    assert recipients_of() == ["cust@test.com"]
    assert "Reply on" in SENT[0]["subject"]


@pytest.mark.asyncio
async def test_customer_reply_emails_the_assignee_only():
    async with AsyncTestClient(app=app) as client:
        admin_headers = await bootstrap(client)
        _, agent_user = await register(client, "erin")
        await client.patch(
            f"/api/users/{agent_user['id']}/role", json={"role": "agent"}, headers=admin_headers
        )
        customer_headers, _ = await register(client, "cust")
        await enable_outbound_email()

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Still broken", "description": "The issue persists."},
                headers=customer_headers,
            )
        ).json()
        await client.patch(
            f"/api/tickets/{ticket['id']}/assign", json={"agent_id": agent_user["id"]}, headers=admin_headers
        )
        SENT.clear()

        await client.post(
            f"/api/tickets/{ticket['id']}/messages", json={"content": "Any news?"}, headers=customer_headers
        )

    assert len(SENT) == 1
    assert recipients_of() == ["erin@test.com"]


@pytest.mark.asyncio
async def test_unassigned_customer_reply_emails_all_staff():
    async with AsyncTestClient(app=app) as client:
        admin_headers = await bootstrap(client)
        _, agent_user = await register(client, "erin")
        await client.patch(
            f"/api/users/{agent_user['id']}/role", json={"role": "agent"}, headers=admin_headers
        )
        customer_headers, _ = await register(client, "cust")
        await enable_outbound_email()

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Nobody owns this", "description": "Unassigned ticket body."},
                headers=customer_headers,
            )
        ).json()
        SENT.clear()

        await client.post(
            f"/api/tickets/{ticket['id']}/messages", json={"content": "Hello?"}, headers=customer_headers
        )

    assert sorted(recipients_of()) == ["admin@test.com", "erin@test.com"]


@pytest.mark.asyncio
async def test_internal_notes_never_email_anyone():
    async with AsyncTestClient(app=app) as client:
        admin_headers = await bootstrap(client)
        customer_headers, _ = await register(client, "cust")
        await enable_outbound_email()

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Internal only", "description": "Ticket with a whisper."},
                headers=customer_headers,
            )
        ).json()
        SENT.clear()

        await client.post(
            f"/api/tickets/{ticket['id']}/messages",
            json={"content": "Secret staff note", "message_type": "whisper"},
            headers=admin_headers,
        )

    assert SENT == []


@pytest.mark.asyncio
async def test_resolving_emails_the_customer():
    async with AsyncTestClient(app=app) as client:
        admin_headers = await bootstrap(client)
        customer_headers, _ = await register(client, "cust")
        await enable_outbound_email()

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Fix me", "description": "Please fix this."},
                headers=customer_headers,
            )
        ).json()
        SENT.clear()

        await client.patch(
            f"/api/tickets/{ticket['id']}/status", json={"status": "resolved"}, headers=admin_headers
        )

    assert len(SENT) == 1
    assert recipients_of() == ["cust@test.com"]
    assert "resolved" in SENT[0]["subject"]


@pytest.mark.asyncio
async def test_assignment_emails_the_new_assignee():
    async with AsyncTestClient(app=app) as client:
        admin_headers = await bootstrap(client)
        _, agent_user = await register(client, "erin")
        await client.patch(
            f"/api/users/{agent_user['id']}/role", json={"role": "agent"}, headers=admin_headers
        )
        customer_headers, _ = await register(client, "cust")
        await enable_outbound_email()

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Assign me", "description": "Needs an owner."},
                headers=customer_headers,
            )
        ).json()
        SENT.clear()

        await client.patch(
            f"/api/tickets/{ticket['id']}/assign", json={"agent_id": agent_user["id"]}, headers=admin_headers
        )

    assert len(SENT) == 1
    assert recipients_of() == ["erin@test.com"]
    assert "assigned to you" in SENT[0]["subject"]


@pytest.mark.asyncio
async def test_nothing_is_sent_while_email_is_disabled():
    async with AsyncTestClient(app=app) as client:
        await bootstrap(client)
        customer_headers, _ = await register(client, "cust")
        await enable_outbound_email(False)

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Silent", "description": "No mail should leave."},
                headers=customer_headers,
            )
        ).json()
        await client.post(
            f"/api/tickets/{ticket['id']}/messages", json={"content": "Hello"}, headers=customer_headers
        )

    assert SENT == []


@pytest.mark.asyncio
async def test_support_inbox_receives_new_tickets():
    async with AsyncTestClient(app=app) as client:
        await bootstrap(client)
        customer_headers, _ = await register(client, "cust")
        await settings_service.set_many(
            {"smtp_enabled": True, "smtp_host": "smtp.test", "support_email": "queue@test.com"}
        )

        await client.post(
            "/api/tickets",
            json={"title": "Queue me", "description": "Goes to the shared inbox."},
            headers=customer_headers,
        )

    assert "queue@test.com" in recipients_of()
