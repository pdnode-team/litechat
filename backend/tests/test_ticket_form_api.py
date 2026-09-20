"""HTTP-level tests for ticket form validation, conditional fields and errors.

Everything here goes through the API on purpose: the point of the exercise is
that a rejected submission comes back as a field-addressed 422 and that an
unexpected failure is logged with enough detail to debug it.
"""
import logging

import pytest
from litestar.testing import AsyncTestClient

from app.main import app

# A schema that exercises every feature added to the form builder:
#   severity   - single choice that also accepts a custom answer
#   browsers   - multiple choice with a custom answer
#   crash_id   - text, mandatory only while severity is High, with a custom message
#   downtime   - number, only visible while severity is High
FIELDS_SCHEMA = [
    {
        "key": "severity",
        "label": "Severity",
        "type": "select",
        "required": True,
        "options": ["Low", "High"],
        "allow_other": True,
    },
    {
        "key": "browsers",
        "label": "Browsers",
        "type": "multi_select",
        "options": ["Chrome", "Firefox"],
        "allow_other": True,
        "other_label": "Another browser",
    },
    {
        "key": "crash_id",
        "label": "Crash ID",
        "type": "text",
        "min_length": 4,
        "error_message": "Give us the full crash id.",
        "required_when": {"field": "severity", "operator": "equals", "value": "High"},
    },
    {
        "key": "downtime",
        "label": "Minutes of downtime",
        "type": "number",
        "min_value": 0,
        "visible_when": {"field": "severity", "operator": "not_equals", "value": "Low"},
    },
]

BASE_TICKET = {
    "title": "Checkout fails",
    "description": "The payment step returns a 500 for every attempt.",
    "priority": "high",
    "category": "technical",
}


async def make_admin(client: AsyncTestClient) -> dict:
    res = await client.post(
        "/api/auth/setup-admin",
        json={
            "email": "admin@formtest.com",
            "username": "formadmin",
            "full_name": "Form Admin",
            "password": "adminpassword123",
        },
    )
    assert res.status_code in (200, 201), res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def make_customer(client: AsyncTestClient) -> tuple[dict, dict]:
    res = await client.post(
        "/api/auth/register",
        json={
            "email": "customer@formtest.com",
            "username": "formcustomer",
            "full_name": "Form Customer",
            "password": "customerpassword123",
        },
    )
    assert res.status_code in (200, 201), res.text
    body = res.json()
    return body["user"], {"Authorization": f"Bearer {body['access_token']}"}


async def make_ticket_type(client: AsyncTestClient, admin: dict, **overrides) -> dict:
    payload = {
        "name": "Bug report",
        "code": "bug",
        "description": "Structured bug reports",
        "fields_schema": FIELDS_SCHEMA,
        "is_active": True,
        **overrides,
    }
    res = await client.post("/api/ticket-types/", json=payload, headers=admin)
    assert res.status_code in (200, 201), res.text
    return res.json()


def error_map(body: dict) -> dict:
    return {entry["field"]: entry for entry in body.get("errors", [])}


async def _login(client: AsyncTestClient) -> str:
    res = await client.post(
        "/api/auth/login",
        json={"username_or_email": "customer@formtest.com", "password": "customerpassword123"},
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_rejected_submission_lists_every_problem_by_field():
    async with AsyncTestClient(app=app) as client:
        admin = await make_admin(client)
        await make_customer(client)
        ticket_type = await make_ticket_type(client, admin)

        res = await client.post(
            "/api/tickets/",
            json={
                **BASE_TICKET,
                "title": "ab",
                "tags": "x" * 501,
                "ticket_type_id": ticket_type["id"],
                "custom_fields": {"severity": "Low", "browsers": ["Edge", "Safari"]},
            },
            headers={"Authorization": f"Bearer {await _login(client)}"},
        )

        assert res.status_code == 422, res.text
        body = res.json()
        assert body["status_code"] == 422
        assert isinstance(body["detail"], str) and body["detail"]

        errors = error_map(body)
        # All four problems are reported together; the client highlights each one.
        assert errors["title"]["code"] == "too_short"
        assert errors["tags"]["code"] == "too_long"
        assert errors["custom_fields.browsers"]["code"] == "too_many_custom_answers"
        # `severity` is required and present, so it is not among the problems.
        assert "custom_fields.severity" not in errors
        for entry in body["errors"]:
            assert set(entry) == {"field", "label", "message", "code"}


@pytest.mark.asyncio
async def test_conditional_requirement_and_custom_message():
    async with AsyncTestClient(app=app) as client:
        admin = await make_admin(client)
        await make_customer(client)
        ticket_type = await make_ticket_type(client, admin)
        customer = {"Authorization": f"Bearer {await _login(client)}"}

        # Low severity: crash_id is not required, so this is accepted.
        ok = await client.post(
            "/api/tickets/",
            json={
                **BASE_TICKET,
                "ticket_type_id": ticket_type["id"],
                "custom_fields": {"severity": "Low"},
            },
            headers=customer,
        )
        assert ok.status_code == 201, ok.text

        # High severity: crash_id becomes mandatory.
        missing = await client.post(
            "/api/tickets/",
            json={
                **BASE_TICKET,
                "ticket_type_id": ticket_type["id"],
                "custom_fields": {"severity": "High"},
            },
            headers=customer,
        )
        assert missing.status_code == 422
        assert error_map(missing.json())["custom_fields.crash_id"]["code"] == "required"

        # Too short, but the administrator supplied the wording.
        short = await client.post(
            "/api/tickets/",
            json={
                **BASE_TICKET,
                "ticket_type_id": ticket_type["id"],
                "custom_fields": {"severity": "High", "crash_id": "abc"},
            },
            headers=customer,
        )
        assert short.status_code == 422
        assert error_map(short.json())["custom_fields.crash_id"]["message"] == "Give us the full crash id."


@pytest.mark.asyncio
async def test_hidden_answers_are_dropped_and_multi_select_round_trips():
    async with AsyncTestClient(app=app) as client:
        admin = await make_admin(client)
        await make_customer(client)
        ticket_type = await make_ticket_type(client, admin)
        customer = {"Authorization": f"Bearer {await _login(client)}"}

        # `downtime` is hidden while severity is Low: the value is discarded
        # rather than stored, so a tampered client cannot inject hidden answers.
        res = await client.post(
            "/api/tickets/",
            json={
                **BASE_TICKET,
                "ticket_type_id": ticket_type["id"],
                "custom_fields": {
                    "severity": "Low",
                    "downtime": 90,
                    "browsers": ["Chrome", "Lynx"],
                },
            },
            headers=customer,
        )
        assert res.status_code == 201, res.text
        assert res.json()["custom_fields"] == {"severity": "Low", "browsers": ["Chrome", "Lynx"]}

        # Same submission with a high severity keeps both the number and the
        # custom "Other" answer, and coerces the number.
        res = await client.post(
            "/api/tickets/",
            json={
                **BASE_TICKET,
                "ticket_type_id": ticket_type["id"],
                "custom_fields": {
                    "severity": "Totally down",
                    "downtime": "45",
                    "crash_id": "CRASH-1234",
                    "browsers": ["Firefox", "Chrome", "Firefox"],
                },
            },
            headers=customer,
        )
        assert res.status_code == 201, res.text
        assert res.json()["custom_fields"] == {
            "severity": "Totally down",
            "browsers": ["Firefox", "Chrome"],
            "crash_id": "CRASH-1234",
            "downtime": 45,
        }


@pytest.mark.asyncio
async def test_unknown_retired_and_missing_targets_are_client_errors():
    async with AsyncTestClient(app=app) as client:
        admin = await make_admin(client)
        await make_customer(client)
        retired = await make_ticket_type(client, admin, code="retired", is_active=False)
        customer = {"Authorization": f"Bearer {await _login(client)}"}

        unknown_app = await client.post(
            "/api/tickets/", json={**BASE_TICKET, "app_id": 9999}, headers=customer
        )
        assert unknown_app.status_code == 422
        assert error_map(unknown_app.json())["app_id"]["code"] == "not_found"

        inactive_type = await client.post(
            "/api/tickets/", json={**BASE_TICKET, "ticket_type_id": retired["id"]}, headers=customer
        )
        assert inactive_type.status_code == 422
        assert error_map(inactive_type.json())["ticket_type_id"]["code"] == "inactive"

        orphan_fields = await client.post(
            "/api/tickets/", json={**BASE_TICKET, "custom_fields": {"severity": "Low"}}, headers=customer
        )
        assert orphan_fields.status_code == 422
        assert error_map(orphan_fields.json())["custom_fields"]["code"] == "unexpected_fields"

        unknown_type = await client.post(
            "/api/tickets/", json={**BASE_TICKET, "ticket_type_id": 4242}, headers=customer
        )
        assert unknown_type.status_code == 422
        assert error_map(unknown_type.json())["ticket_type_id"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_admin_schema_is_linted_before_it_is_stored():
    async with AsyncTestClient(app=app) as client:
        admin = await make_admin(client)

        duplicate = await client.post(
            "/api/ticket-types/",
            json={
                "name": "Broken",
                "code": "broken",
                "fields_schema": [
                    {"key": "a", "label": "A"},
                    {"key": "a", "label": "A again"},
                ],
            },
            headers=admin,
        )
        assert duplicate.status_code == 422
        assert error_map(duplicate.json())["fields_schema.1"]["code"] == "duplicate_key"

        bad_condition = await client.post(
            "/api/ticket-types/",
            json={
                "name": "Broken too",
                "code": "broken-too",
                "fields_schema": [
                    {"key": "a", "label": "A", "visible_when": {"field": "ghost", "operator": "is_answered"}}
                ],
            },
            headers=admin,
        )
        assert bad_condition.status_code == 422
        assert error_map(bad_condition.json())["fields_schema.0"]["code"] == "unknown_reference"

        no_options = await client.post(
            "/api/ticket-types/",
            json={"name": "Broken three", "code": "broken-three", "fields_schema": [{"key": "a", "label": "A", "type": "select"}]},
            headers=admin,
        )
        # Rejected by the field definition itself, before the schema linter runs.
        assert no_options.status_code in (400, 422)
        assert "option" in no_options.json()["detail"].lower()


@pytest.mark.asyncio
async def test_request_id_is_returned_and_unhandled_errors_are_logged(caplog, monkeypatch):
    async with AsyncTestClient(app=app) as client:
        admin = await make_admin(client)
        await make_customer(client)
        customer = {"Authorization": f"Bearer {await _login(client)}"}

        # Every response carries the correlation id, even a plain 200.
        healthy = await client.get("/api/health")
        assert healthy.status_code == 200
        assert healthy.headers.get("x-request-id")

        # A client-supplied id is honoured so a frontend trace can be followed
        # across services.
        echoed = await client.get("/api/health", headers={"X-Request-ID": "trace-from-the-client"})
        assert echoed.headers["x-request-id"] == "trace-from-the-client"

        # A hostile id is replaced rather than written into the log.
        rejected = await client.get("/api/health", headers={"X-Request-ID": "bad id\nwith newline"})
        assert rejected.headers["x-request-id"] != "bad id\nwith newline"

        def boom(*args, **kwargs):
            raise RuntimeError("database exploded")

        monkeypatch.setattr("app.controllers.tickets.build_ticket_response", boom)

        with caplog.at_level(logging.ERROR, logger="litechat.errors"):
            res = await client.post("/api/tickets/", json=BASE_TICKET, headers=customer)

        assert res.status_code == 500, res.text
        body = res.json()
        assert body["request_id"]
        assert body["request_id"] == res.headers["x-request-id"]
        assert body["request_id"] in body["detail"]

        # The operator can grep the request id and find the real cause.
        assert "Unhandled RuntimeError on POST /api/tickets" in caplog.text
        assert "database exploded" in caplog.text
        logged = next(record for record in caplog.records if record.name == "litechat.errors")
        assert logged.exc_info is not None
        assert logged.request_id == body["request_id"]


@pytest.mark.asyncio
async def test_missing_authentication_still_reports_its_status():
    """A 401 must stay a 401 - the 500 handler must not swallow business errors."""
    async with AsyncTestClient(app=app) as client:
        res = await client.post("/api/tickets/", json=BASE_TICKET)
        assert res.status_code == 401
        assert res.headers.get("x-request-id")

        missing = await client.get("/api/tickets/9999")
        assert missing.status_code == 401
