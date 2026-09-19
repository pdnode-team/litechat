"""Runtime settings API, environment fallback and secret handling."""
import pytest
from litestar.testing import AsyncTestClient

from app.db.session import async_session_factory
from app.main import app
from app.models.app_setting import AppSetting
from app.services import secret_box, settings_service


@pytest.fixture(autouse=True)
def clear_settings_cache():
    settings_service.invalidate()
    yield
    settings_service.invalidate()


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
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def register_customer(client: AsyncTestClient) -> dict:
    res = await client.post(
        "/api/auth/register",
        json={
            "email": "cust@test.com",
            "username": "cust_user",
            "full_name": "Cust User",
            "password": "customerpass123",
        },
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_secrets_round_trip_and_are_not_plaintext():
    encrypted = secret_box.encrypt("hunter2")
    assert encrypted != "hunter2"
    assert "hunter2" not in encrypted
    assert secret_box.is_encrypted(encrypted)
    assert secret_box.decrypt(encrypted) == "hunter2"


def test_decrypting_garbage_is_treated_as_unset():
    assert secret_box.decrypt("enc:v1:not-a-real-token") == ""
    assert secret_box.decrypt("") == ""
    # A value written before encryption existed is returned as-is.
    assert secret_box.decrypt("legacy-plain") == "legacy-plain"


@pytest.mark.asyncio
async def test_settings_are_admin_only():
    async with AsyncTestClient(app=app) as client:
        await bootstrap_admin(client)
        customer = await register_customer(client)

        assert (await client.get("/api/settings", headers=customer)).status_code == 403
        assert (await client.get("/api/settings")).status_code == 401
        assert (
            await client.put("/api/settings/email", json={"smtp_host": "x"}, headers=customer)
        ).status_code == 403


@pytest.mark.asyncio
async def test_email_settings_round_trip_and_mask_the_password():
    async with AsyncTestClient(app=app) as client:
        admin = await bootstrap_admin(client)

        assert (await client.get("/api/settings", headers=admin)).json()["smtp_password_set"] is False

        res = await client.put(
            "/api/settings/email",
            json={
                "smtp_enabled": True,
                "smtp_host": "smtp.example.com",
                "smtp_port": 2525,
                "smtp_username": "mailer",
                "smtp_password": "s3cret",
                "smtp_from": "help@example.com",
            },
            headers=admin,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["smtp_host"] == "smtp.example.com"
        assert body["smtp_port"] == 2525
        assert body["smtp_use_tls"] is True
        # The secret is never echoed back.
        assert body["smtp_password_set"] is True
        assert "smtp_password" not in body

        # And it is stored encrypted, not in clear text.
        values = await settings_service.get_all(force=True)
        assert values["smtp_password"] == "s3cret"
        async with async_session_factory() as session:
            row = await session.get(AppSetting, "smtp_password")
            assert row is not None
            assert row.value != "s3cret"
            assert secret_box.is_encrypted(row.value)


@pytest.mark.asyncio
async def test_omitted_fields_are_left_alone():
    async with AsyncTestClient(app=app) as client:
        admin = await bootstrap_admin(client)
        await client.put(
            "/api/settings/email",
            json={"smtp_host": "first.example.com", "smtp_port": 1000},
            headers=admin,
        )
        await client.put("/api/settings/email", json={"smtp_port": 2000}, headers=admin)

        body = (await client.get("/api/settings", headers=admin)).json()

    assert body["smtp_host"] == "first.example.com"
    assert body["smtp_port"] == 2000


@pytest.mark.asyncio
async def test_notification_toggles_round_trip():
    async with AsyncTestClient(app=app) as client:
        admin = await bootstrap_admin(client)
        res = await client.put(
            "/api/settings/notifications",
            json={"notify_new_ticket": False, "support_email": "queue@example.com"},
            headers=admin,
        )
        body = res.json()

    assert body["notify_new_ticket"] is False
    # Untouched toggles keep their defaults.
    assert body["notify_ticket_reply"] is True
    assert body["support_email"] == "queue@example.com"


@pytest.mark.asyncio
async def test_smtp_enabled_defaults_to_host_presence():
    async with AsyncTestClient(app=app) as client:
        admin = await bootstrap_admin(client)
        # With no host and no explicit flag, email is off.
        assert (await client.get("/api/settings", headers=admin)).json()["smtp_enabled"] is False

        await client.put("/api/settings/email", json={"smtp_host": "smtp.example.com"}, headers=admin)
        assert (await client.get("/api/settings", headers=admin)).json()["smtp_enabled"] is True


@pytest.mark.asyncio
async def test_unknown_setting_is_rejected():
    with pytest.raises(ValueError):
        await settings_service.set_many({"not_a_real_setting": "x"})


@pytest.mark.asyncio
async def test_test_email_reports_when_smtp_is_not_configured():
    async with AsyncTestClient(app=app) as client:
        admin = await bootstrap_admin(client)
        res = await client.post(
            "/api/settings/email/test", json={"to": "someone@example.com"}, headers=admin
        )
        body = res.json()

    assert res.status_code in (200, 201)
    assert body["sent"] is False
    assert "disabled" in body["detail"].lower() or "host" in body["detail"].lower()


@pytest.mark.asyncio
async def test_email_settings_survive_a_cache_reset():
    async with AsyncTestClient(app=app) as client:
        admin = await bootstrap_admin(client)
        await client.put("/api/settings/email", json={"smtp_from": "help@example.com"}, headers=admin)

    settings_service.invalidate()
    assert await settings_service.get("smtp_from") == "help@example.com"
