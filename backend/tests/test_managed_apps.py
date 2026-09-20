"""Managed applications: every rejected input must come back as a 422, not a 500.

Creating an app used to be able to fail with a raw database error (a duplicate
`code`, or a value longer than its column) which the client saw as
"500 Internal Server Error" with nothing to act on.
"""
import pytest
from litestar.testing import AsyncTestClient
from sqlalchemy.exc import IntegrityError

from app.db.errors import is_unique_violation
from app.main import app


async def admin_headers(client: AsyncTestClient) -> dict:
    res = await client.post(
        "/api/auth/setup-admin",
        json={
            "email": "admin@appstest.com",
            "username": "apps_admin",
            "full_name": "Apps Admin",
            "password": "adminpassword123",
        },
    )
    assert res.status_code in (200, 201), res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def errors_by_field(res) -> dict:
    return {entry["field"]: entry for entry in res.json().get("errors", [])}


def test_unique_violation_detection_does_not_blame_a_sequence_collision():
    """Only the named constraint counts, or a broken id sequence would be
    reported to the user as "this code already exists"."""
    hints = ("ix_managed_apps_code", "managed_apps.code")

    postgres = IntegrityError(
        "INSERT ...", {}, Exception('duplicate key value violates unique constraint "ix_managed_apps_code"')
    )
    assert is_unique_violation(postgres, hints)

    sqlite = IntegrityError("INSERT ...", {}, Exception("UNIQUE constraint failed: managed_apps.code"))
    assert is_unique_violation(sqlite, hints)

    sequence = IntegrityError(
        "INSERT ...", {}, Exception('duplicate key value violates unique constraint "managed_apps_pkey"')
    )
    assert not is_unique_violation(sequence, hints)


@pytest.mark.asyncio
async def test_valid_application_is_created_and_normalised():
    async with AsyncTestClient(app=app) as client:
        admin = await admin_headers(client)

        res = await client.post(
            "/api/apps/",
            json={"name": "  Cloud Dashboard  ", "code": "  CLOUD_DASH  ", "base_url": "https://dash.example.com"},
            headers=admin,
        )
        assert res.status_code in (200, 201), res.text
        body = res.json()
        assert body["name"] == "Cloud Dashboard"
        assert body["code"] == "cloud_dash"
        assert body["base_url"] == "https://dash.example.com"


@pytest.mark.asyncio
async def test_duplicate_code_is_a_field_error_not_a_database_error():
    async with AsyncTestClient(app=app) as client:
        admin = await admin_headers(client)

        first = await client.post("/api/apps/", json={"name": "Portal", "code": "portal"}, headers=admin)
        assert first.status_code in (200, 201)

        # Different case: the stored code is lowercase, and the pre-check used to
        # compare the raw value, so this reached the unique index and blew up.
        second = await client.post("/api/apps/", json={"name": "Portal again", "code": "PORTAL"}, headers=admin)
        assert second.status_code == 422, second.text
        assert errors_by_field(second)["code"]["code"] == "duplicate"


@pytest.mark.asyncio
async def test_values_longer_than_their_column_are_rejected_up_front():
    async with AsyncTestClient(app=app) as client:
        admin = await admin_headers(client)

        long_name = await client.post(
            "/api/apps/", json={"name": "N" * 101, "code": "long_name"}, headers=admin
        )
        assert long_name.status_code == 422
        assert errors_by_field(long_name)["name"]["code"] == "too_long"

        long_url = await client.post(
            "/api/apps/",
            json={"name": "Long URL", "code": "long_url", "base_url": "https://example.com/" + "x" * 250},
            headers=admin,
        )
        assert long_url.status_code == 422
        assert errors_by_field(long_url)["base_url"]["code"] == "too_long"

        long_code = await client.post(
            "/api/apps/", json={"name": "Long code", "code": "c" * 51}, headers=admin
        )
        assert long_code.status_code == 422
        assert errors_by_field(long_code)["code"]["code"] == "too_long"


@pytest.mark.asyncio
async def test_code_format_and_missing_fields_are_reported_together():
    async with AsyncTestClient(app=app) as client:
        admin = await admin_headers(client)

        res = await client.post("/api/apps/", json={"name": "   ", "code": "My App!"}, headers=admin)
        assert res.status_code == 422
        errors = errors_by_field(res)
        assert errors["name"]["code"] == "required"
        assert errors["code"]["code"] == "invalid_format"


@pytest.mark.asyncio
async def test_base_url_must_be_absolute():
    async with AsyncTestClient(app=app) as client:
        admin = await admin_headers(client)

        res = await client.post(
            "/api/apps/", json={"name": "Bad URL", "code": "bad_url", "base_url": "example.com/x"}, headers=admin
        )
        assert res.status_code == 422
        assert errors_by_field(res)["base_url"]["code"] == "invalid_url"


@pytest.mark.asyncio
async def test_updating_onto_existing_code_is_rejected_and_partial_edits_work():
    async with AsyncTestClient(app=app) as client:
        admin = await admin_headers(client)

        await client.post("/api/apps/", json={"name": "First", "code": "first"}, headers=admin)
        second = (
            await client.post(
                "/api/apps/", json={"name": "Second", "code": "second", "base_url": "https://b.example.com"}, headers=admin
            )
        ).json()

        clash = await client.put(f"/api/apps/{second['id']}", json={"code": "first"}, headers=admin)
        assert clash.status_code == 422, clash.text
        assert errors_by_field(clash)["code"]["code"] == "duplicate"

        # Renaming only must leave the code alone.
        renamed = await client.put(f"/api/apps/{second['id']}", json={"name": "Second (renamed)"}, headers=admin)
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Second (renamed)"
        assert renamed.json()["code"] == "second"

        # An empty string clears the base URL.
        cleared = await client.put(f"/api/apps/{second['id']}", json={"base_url": ""}, headers=admin)
        assert cleared.status_code == 200
        assert cleared.json()["base_url"] is None


@pytest.mark.asyncio
async def test_over_long_faq_and_macro_values_are_rejected():
    """The same column-overflow trap existed on the other admin catalogues."""
    async with AsyncTestClient(app=app) as client:
        admin = await admin_headers(client)

        faq = await client.post(
            "/api/faq/",
            json={"category": "general", "question": "Q" * 256, "answer": "An answer."},
            headers=admin,
        )
        assert faq.status_code in (400, 422), faq.text

        macro = await client.post(
            "/api/canned-responses/",
            json={"shortcut": "s" * 51, "title": "Title", "content": "Body"},
            headers=admin,
        )
        assert macro.status_code in (400, 422), macro.text


@pytest.mark.asyncio
async def test_shortcut_limit_applies_after_the_leading_slash_is_added():
    """A 50-character shortcut becomes 51 once the slash is prepended."""
    async with AsyncTestClient(app=app) as client:
        admin = await admin_headers(client)

        too_long = await client.post(
            "/api/canned-responses/",
            json={"shortcut": "s" * 50, "title": "Title", "content": "Body"},
            headers=admin,
        )
        assert too_long.status_code == 422, too_long.text
        assert errors_by_field(too_long)["shortcut"]["code"] == "too_long"

        just_fits = await client.post(
            "/api/canned-responses/",
            json={"shortcut": "s" * 49, "title": "Title", "content": "Body"},
            headers=admin,
        )
        assert just_fits.status_code in (200, 201), just_fits.text
        assert just_fits.json()["shortcut"] == "/" + "s" * 49


@pytest.mark.asyncio
async def test_renaming_a_macro_onto_an_existing_shortcut_is_a_field_error():
    async with AsyncTestClient(app=app) as client:
        admin = await admin_headers(client)

        await client.post(
            "/api/canned-responses/",
            json={"shortcut": "/refund", "title": "Refund", "content": "Body"},
            headers=admin,
        )
        second = (
            await client.post(
                "/api/canned-responses/",
                json={"shortcut": "/receipt", "title": "Receipt", "content": "Body"},
                headers=admin,
            )
        ).json()

        clash = await client.patch(
            f"/api/canned-responses/{second['id']}", json={"shortcut": "refund"}, headers=admin
        )
        assert clash.status_code == 422, clash.text
        assert errors_by_field(clash)["shortcut"]["code"] == "duplicate"
