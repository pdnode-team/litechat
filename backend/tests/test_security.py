"""Regression tests for the security hardening: bootstrap, RBAC, uploads, tokens."""
import jwt
import pytest
from litestar.testing import AsyncTestClient

from app.config import JWT_ALGORITHM, JWT_SECRET_KEY, UPLOAD_DIR
from app.main import app

ADMIN = {
    "email": "root@test.com",
    "username": "root_admin",
    "full_name": "Root Admin",
    "password": "rootpass123",
}


async def bootstrap_admin(client: AsyncTestClient) -> dict:
    """Create the first administrator and return auth headers."""
    res = await client.post("/api/auth/setup-admin", json=ADMIN)
    assert res.status_code in (200, 201), res.text
    assert res.json()["user"]["role"] == "admin"
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def register_customer(client: AsyncTestClient, tag: str) -> tuple[dict, dict]:
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
    return {"Authorization": f"Bearer {res.json()['access_token']}"}, res.json()["user"]


@pytest.mark.asyncio
async def test_bootstrap_status_is_one_shot():
    async with AsyncTestClient(app=app) as client:
        assert (await client.get("/api/auth/bootstrap-status")).json() == {"needs_setup": True}

        await bootstrap_admin(client)

        assert (await client.get("/api/auth/bootstrap-status")).json() == {"needs_setup": False}
        # A second bootstrap attempt must be refused.
        assert (await client.post("/api/auth/setup-admin", json=ADMIN)).status_code == 403


@pytest.mark.asyncio
async def test_public_registration_never_grants_privileges():
    async with AsyncTestClient(app=app) as client:
        res = await client.post(
            "/api/auth/register",
            json={
                "email": "escalate@test.com",
                "username": "escalate",
                "full_name": "Escalate Me",
                "password": "customerpass123",
                # A client must not be able to request a role at all.
                "role": "admin",
            },
        )
        assert res.status_code in (200, 201)
        assert res.json()["user"]["role"] == "customer"


@pytest.mark.asyncio
async def test_weak_passwords_are_rejected():
    async with AsyncTestClient(app=app) as client:
        for password in ["short1", "alllettersonly", "12345678"]:
            res = await client.post(
                "/api/auth/register",
                json={
                    "email": f"weak{len(password)}@test.com",
                    "username": f"weak{len(password)}",
                    "full_name": "Weak Password",
                    "password": password,
                },
            )
            assert res.status_code == 400, f"{password!r} unexpectedly accepted"


@pytest.mark.asyncio
async def test_upload_rejects_bad_extension_and_contains_traversal():
    async with AsyncTestClient(app=app) as client:
        headers, _ = await register_customer(client, "uploader")

        # Disallowed extension (executable) is refused.
        bad = await client.post(
            "/api/upload", files={"data": ("payload.exe", b"MZ", "application/octet-stream")}, headers=headers
        )
        assert bad.status_code == 400

        # A traversal filename must be reduced to a basename inside UPLOAD_DIR.
        res = await client.post(
            "/api/upload",
            files={"data": ("../../../escaped.txt", b"traversal", "text/plain")},
            headers=headers,
        )
        assert res.status_code in (200, 201), res.text

        stored_name = res.json()["url"].rsplit("/", 1)[-1]
        stored_path = (UPLOAD_DIR / stored_name).resolve()
        try:
            assert stored_path.parent == UPLOAD_DIR.resolve()
            assert stored_path.exists()
            # Nothing may be written outside the upload directory.
            assert not (UPLOAD_DIR.parent / "escaped.txt").exists()
            assert not (UPLOAD_DIR.parent.parent / "escaped.txt").exists()
        finally:
            stored_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_non_numeric_token_subject_is_unauthorized_not_a_crash():
    async with AsyncTestClient(app=app) as client:
        token = jwt.encode({"sub": "not-an-int", "role": "admin"}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_tokens_signed_with_a_guessable_secret_are_rejected():
    async with AsyncTestClient(app=app) as client:
        await bootstrap_admin(client)
        forged = jwt.encode(
            {"sub": "1", "role": "admin", "name": "Attacker"},
            "litechat-super-secret-key-change-in-production-382947192",
            algorithm=JWT_ALGORITHM,
        )
        res = await client.get("/api/users", headers={"Authorization": f"Bearer {forged}"})
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_csat_requires_ownership_and_staff_cannot_rate():
    async with AsyncTestClient(app=app) as client:
        admin_headers = await bootstrap_admin(client)
        owner_headers, _ = await register_customer(client, "owner")
        other_headers, _ = await register_customer(client, "other")

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Rate me", "description": "Please rate this ticket."},
                headers=owner_headers,
            )
        ).json()

        await client.patch(f"/api/tickets/{ticket['id']}/status", json={"status": "resolved"}, headers=owner_headers)

        # A different customer must not be able to read or write this rating.
        assert (await client.get(f"/api/tickets/{ticket['id']}/csat", headers=other_headers)).status_code == 403
        assert (
            await client.post(f"/api/tickets/{ticket['id']}/csat", json={"score": 1}, headers=other_headers)
        ).status_code == 403

        # Staff must not be able to rate on the customer's behalf.
        assert (
            await client.post(f"/api/tickets/{ticket['id']}/csat", json={"score": 1}, headers=admin_headers)
        ).status_code == 403

        # The owner can, and the rating is attributed to the ticket's customer.
        ok = await client.post(
            f"/api/tickets/{ticket['id']}/csat",
            json={"score": 5, "comment": "Great"},
            headers=owner_headers,
        )
        assert ok.status_code in (200, 201)
        assert ok.json()["customer_id"] == ticket["customer_id"]

        # And the owner can read it back.
        assert (await client.get(f"/api/tickets/{ticket['id']}/csat", headers=owner_headers)).status_code == 200


@pytest.mark.asyncio
async def test_customers_cannot_forge_system_messages():
    async with AsyncTestClient(app=app) as client:
        await bootstrap_admin(client)
        headers, _ = await register_customer(client, "spoofer")

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Spoof attempt", "description": "Attempting to forge an event."},
                headers=headers,
            )
        ).json()

        res = await client.post(
            f"/api/tickets/{ticket['id']}/messages",
            json={"content": "Ticket resolved by Fake Admin", "message_type": "action_card"},
            headers=headers,
        )
        assert res.status_code in (200, 201)
        # The spoofed type must be coerced back to a normal message.
        assert res.json()["message_type"] == "text"


@pytest.mark.asyncio
async def test_staff_only_endpoints_are_not_publicly_readable():
    async with AsyncTestClient(app=app) as client:
        await bootstrap_admin(client)
        for path in ["/api/apps", "/api/ticket-types", "/api/users", "/api/analytics/summary"]:
            res = await client.get(path)
            assert res.status_code == 401, f"{path} leaked to anonymous callers"
