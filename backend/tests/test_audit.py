"""Audit log writes and the admin list endpoint."""
import json

import pytest
from litestar.testing import AsyncTestClient

from app.main import app
from app.services import audit


@pytest.mark.asyncio
async def test_role_change_and_settings_are_audited_without_secrets():
    async with AsyncTestClient(app=app) as client:
        admin = await client.post(
            "/api/auth/setup-admin",
            json={
                "email": "audit-admin@formtest.com",
                "username": "audit_admin",
                "full_name": "Audit Admin",
                "password": "rootpass123",
            },
        )
        headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
        customer = await client.post(
            "/api/auth/register",
            json={
                "email": "audited@formtest.com",
                "username": "audited_user",
                "full_name": "Audited User",
                "password": "customerpass123",
            },
        )
        user_id = customer.json()["user"]["id"]
        await client.patch(f"/api/users/{user_id}/role", json={"role": "agent"}, headers=headers)
        await client.put(
            "/api/settings/email",
            json={"smtp_host": "smtp.example.com", "smtp_password": "super-secret"},
            headers=headers,
        )

        listed = await client.get("/api/audit-logs", headers=headers)
        assert listed.status_code == 200, listed.text
        actions = {item["action"]: item for item in listed.json()["items"]}
        assert "user.role_changed" in actions
        assert "settings.email_updated" in actions
        after = json.loads(actions["settings.email_updated"]["after_json"])
        assert after["smtp_password"] == "[redacted]"
        assert "super-secret" not in json.dumps(listed.json())

        forbidden = await client.get(
            "/api/audit-logs",
            headers={"Authorization": f"Bearer {customer.json()['access_token']}"},
        )
        assert forbidden.status_code == 403


def test_audit_record_scrubs_passwords_in_isolation():
    dumped = audit._dump({"smtp_password": "plain", "nested": {"token": "abc"}})
    parsed = json.loads(dumped)
    assert parsed["smtp_password"] == "[redacted]"
    assert parsed["nested"]["token"] == "[redacted]"
