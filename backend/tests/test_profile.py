"""Profile edits: display name, avatar URL, email change."""
import pytest
from litestar.testing import AsyncTestClient

import app.controllers.auth as auth_module
from app.main import app


async def register(client: AsyncTestClient, tag: str, password: str = "customerpass123") -> dict:
    res = await client.post(
        "/api/auth/register",
        json={
            "email": f"{tag}@formtest.com",
            "username": f"user_{tag}",
            "full_name": f"User {tag.title()}",
            "password": password,
        },
    )
    assert res.status_code in (200, 201), res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def captured_mail(monkeypatch):
    sent: dict[str, str] = {}

    async def fake_change(to: str, raw_token: str) -> None:
        sent["change"] = raw_token
        sent["change_to"] = to

    async def fake_notice(to: str, new_email: str) -> None:
        sent["notice_to"] = to
        sent["notice_new"] = new_email

    monkeypatch.setattr(auth_module, "send_email_change_verification", fake_change)
    monkeypatch.setattr(auth_module, "send_email_change_notice", fake_notice)
    return sent


@pytest.mark.asyncio
async def test_patch_me_updates_name_and_avatar():
    async with AsyncTestClient(app=app) as client:
        headers = await register(client, "profile")
        res = await client.patch(
            "/api/users/me",
            json={"full_name": "Ada Lovelace", "avatar_url": "https://example.com/ada.png"},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["full_name"] == "Ada Lovelace"
        assert body["avatar_url"] == "https://example.com/ada.png"
        me = (await client.get("/api/auth/me", headers=headers)).json()
        assert me["full_name"] == "Ada Lovelace"


@pytest.mark.asyncio
async def test_patch_me_rejects_overlong_and_javascript_urls():
    async with AsyncTestClient(app=app) as client:
        headers = await register(client, "toolong")
        too_long = await client.patch(
            "/api/users/me",
            json={"full_name": "x" * 151},
            headers=headers,
        )
        assert too_long.status_code == 422
        assert too_long.json()["errors"][0]["field"] == "full_name"

        bad_url = await client.patch(
            "/api/users/me",
            json={"avatar_url": "javascript:alert(1)"},
            headers=headers,
        )
        assert bad_url.status_code == 422
        assert bad_url.json()["errors"][0]["field"] == "avatar_url"


@pytest.mark.asyncio
async def test_patch_me_cannot_set_role_or_email():
    async with AsyncTestClient(app=app) as client:
        headers = await register(client, "norole")
        res = await client.patch(
            "/api/users/me",
            json={"full_name": "Still Customer", "role": "admin", "email": "other@formtest.com"},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["role"] == "customer"
        assert body["email"] == "norole@formtest.com"


@pytest.mark.asyncio
async def test_email_change_requires_confirmation(captured_mail):
    async with AsyncTestClient(app=app) as client:
        headers = await register(client, "mailswap", password="customerpass123")
        start = await client.post(
            "/api/auth/change-email",
            json={"password": "customerpass123", "new_email": "fresh@formtest.com"},
            headers=headers,
        )
        assert start.status_code in (200, 201), start.text
        assert captured_mail["change_to"] == "fresh@formtest.com"
        assert captured_mail["notice_to"] == "mailswap@formtest.com"

        me = (await client.get("/api/auth/me", headers=headers)).json()
        assert me["email"] == "mailswap@formtest.com"

        confirm = await client.post(
            "/api/auth/verify-email-change", json={"token": captured_mail["change"]}
        )
        assert confirm.status_code in (200, 201), confirm.text
        me = (await client.get("/api/auth/me", headers=headers)).json()
        assert me["email"] == "fresh@formtest.com"
        assert me["email_verified"] is True
