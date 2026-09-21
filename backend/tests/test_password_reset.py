"""Password reset, email verification and change-password flows."""
import pytest
from litestar.testing import AsyncTestClient

import app.controllers.auth as auth_module
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


async def register(client: AsyncTestClient, tag: str, password: str = "customerpass123") -> dict:
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
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def captured_mail(monkeypatch):
    """Intercept outbound mail and expose the tokens the app generated."""
    sent: dict[str, str] = {}

    async def fake_reset(to: str, raw_token: str) -> None:
        sent["reset"] = raw_token
        sent["reset_to"] = to

    async def fake_verify(to: str, raw_token: str) -> None:
        sent["verify"] = raw_token
        sent["verify_to"] = to

    # The controller imported these names directly, so patch them there.
    monkeypatch.setattr(auth_module, "send_password_reset_email", fake_reset)
    monkeypatch.setattr(auth_module, "send_email_verification_email", fake_verify)
    return sent


@pytest.mark.asyncio
async def test_registration_sends_a_verification_email(captured_mail):
    async with AsyncTestClient(app=app) as client:
        body = (await register(client, "newbie")).get("Authorization")
        assert body
        assert captured_mail["verify_to"] == "newbie@test.com"
        assert captured_mail.get("verify")


@pytest.mark.asyncio
async def test_unverified_users_can_still_sign_in(captured_mail):
    """Verification is advisory: it must never lock an account out."""
    async with AsyncTestClient(app=app) as client:
        registered = await client.post(
            "/api/auth/register",
            json={
                "email": "lazy@test.com",
                "username": "lazy_user",
                "full_name": "Lazy User",
                "password": "customerpass123",
            },
        )
        assert registered.json()["user"]["email_verified"] is False

        login = await client.post(
            "/api/auth/login",
            json={"username_or_email": "lazy@test.com", "password": "customerpass123"},
        )
        assert login.status_code in (200, 201)
        assert login.json()["user"]["email_verified"] is False


@pytest.mark.asyncio
async def test_email_verification_marks_the_account_confirmed(captured_mail):
    async with AsyncTestClient(app=app) as client:
        headers = await register(client, "verifyme")
        token = captured_mail["verify"]

        assert (await client.post("/api/auth/verify-email", json={"token": "nonsense-token"})).status_code == 400

        ok = await client.post("/api/auth/verify-email", json={"token": token})
        assert ok.status_code in (200, 201)
        assert (await client.get("/api/auth/me", headers=headers)).json()["email_verified"] is True

        # Single use.
        assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 400


@pytest.mark.asyncio
async def test_password_reset_round_trip(captured_mail):
    async with AsyncTestClient(app=app) as client:
        headers = await register(client, "forgetful", password="oldpassword123")

        # Unknown addresses get the same response as known ones (no enumeration).
        unknown = await client.post("/api/auth/forgot-password", json={"email": "nobody@test.com"})
        known = await client.post("/api/auth/forgot-password", json={"email": "forgetful@test.com"})
        assert unknown.status_code == known.status_code == 202
        assert "reset" in captured_mail

        token = captured_mail["reset"]

        assert (
            await client.post("/api/auth/reset-password", json={"token": "bad-token-value", "new_password": "whatever123"})
        ).status_code == 400
        # Weak replacement passwords are still rejected.
        assert (
            await client.post("/api/auth/reset-password", json={"token": token, "new_password": "short"})
        ).status_code == 400

        ok = await client.post("/api/auth/reset-password", json={"token": token, "new_password": "brandnew123"})
        assert ok.status_code in (200, 201)

        # The token cannot be replayed.
        assert (
            await client.post("/api/auth/reset-password", json={"token": token, "new_password": "another123"})
        ).status_code == 400

        # Old password no longer works; the new one does.
        assert (
            await client.post(
                "/api/auth/login", json={"username_or_email": "forgetful@test.com", "password": "oldpassword123"}
            )
        ).status_code == 401
        new_login = await client.post(
            "/api/auth/login", json={"username_or_email": "forgetful@test.com", "password": "brandnew123"}
        )
        assert new_login.status_code in (200, 201)
        assert new_login.json()["user"]["email"] == "forgetful@test.com"

        # The session issued before the reset is revoked.
        assert (await client.get("/api/auth/me", headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_issuing_a_new_reset_token_invalidates_the_previous_one(captured_mail):
    async with AsyncTestClient(app=app) as client:
        await register(client, "twice")
        await client.post("/api/auth/forgot-password", json={"email": "twice@test.com"})
        first = captured_mail["reset"]

        await client.post("/api/auth/forgot-password", json={"email": "twice@test.com"})
        second = captured_mail["reset"]
        assert first != second

        assert (
            await client.post("/api/auth/reset-password", json={"token": first, "new_password": "validpass123"})
        ).status_code == 400
        assert (
            await client.post("/api/auth/reset-password", json={"token": second, "new_password": "validpass123"})
        ).status_code in (200, 201)


@pytest.mark.asyncio
async def test_change_password_requires_the_current_one(captured_mail):
    async with AsyncTestClient(app=app) as client:
        headers = await register(client, "changer", password="currentpass123")

        wrong = await client.post(
            "/api/auth/change-password",
            json={"current_password": "notmypassword", "new_password": "newpass12345"},
            headers=headers,
        )
        assert wrong.status_code == 400

        ok = await client.post(
            "/api/auth/change-password",
            json={"current_password": "currentpass123", "new_password": "newpass12345"},
            headers=headers,
        )
        assert ok.status_code in (200, 201)

        assert (
            await client.post(
                "/api/auth/login", json={"username_or_email": "changer@test.com", "password": "newpass12345"}
            )
        ).status_code in (200, 201)

        assert (await client.get("/api/auth/me", headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_resend_verification_is_authenticated(captured_mail):
    async with AsyncTestClient(app=app) as client:
        assert (await client.post("/api/auth/resend-verification")).status_code == 401

        headers = await register(client, "resender")
        first_token = captured_mail["verify"]

        resend = await client.post("/api/auth/resend-verification", headers=headers)
        assert resend.status_code in (200, 201)
        assert captured_mail["verify"] != first_token

        # Once confirmed, resending is a no-op.
        await client.post("/api/auth/verify-email", json={"token": captured_mail["verify"]})
        again = await client.post("/api/auth/resend-verification", headers=headers)
        assert again.status_code in (200, 201)
