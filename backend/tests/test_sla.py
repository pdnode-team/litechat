"""SLA deadlines: calendar time by default, business hours when enabled."""
from datetime import datetime

import pytest

from app.services.sla_service import SlaPolicy, add_business_minutes, calculate_sla_deadlines


def _policy(**overrides) -> SlaPolicy:
    values = {
        "sla_first_urgent": 15,
        "sla_first_high": 30,
        "sla_first_medium": 120,
        "sla_first_low": 480,
        "sla_resolution_urgent": 120,
        "sla_resolution_high": 360,
        "sla_resolution_medium": 1440,
        "sla_resolution_low": 2880,
        "sla_business_hours_enabled": True,
        "sla_weekdays": "mon,tue,wed,thu,fri",
        "sla_start": "09:00",
        "sla_end": "18:00",
        "sla_timezone": "UTC",
        "sla_observe_holidays": False,
    }
    values.update(overrides)
    return SlaPolicy.from_settings(values)


@pytest.mark.asyncio
async def test_calendar_time_is_the_default():
    start = datetime(2026, 3, 6, 17, 0, 0)  # Friday 17:00 UTC
    first, resolution = await calculate_sla_deadlines("medium", start, policy=_policy(sla_business_hours_enabled=False))
    assert first == datetime(2026, 3, 6, 19, 0, 0)
    assert resolution == datetime(2026, 3, 7, 17, 0, 0)


def test_friday_near_close_rolls_to_monday():
    # Friday 17:50, 30 minutes of first-response time, hours 09:00-18:00.
    start = datetime(2026, 3, 6, 17, 50, 0)
    due = add_business_minutes(start, 30, _policy())
    assert due == datetime(2026, 3, 9, 9, 20, 0)


def test_weekend_ticket_starts_monday_morning():
    start = datetime(2026, 3, 7, 11, 0, 0)  # Saturday
    due = add_business_minutes(start, 15, _policy())
    assert due == datetime(2026, 3, 9, 9, 15, 0)


def test_cross_month_boundary():
    # Friday 31 Jan 2025 17:00; 120 minutes of business time.
    start = datetime(2025, 1, 31, 17, 0, 0)
    due = add_business_minutes(start, 120, _policy())
    # 60 minutes Friday + 60 minutes Monday 3 Feb 09:00.
    assert due == datetime(2025, 2, 3, 10, 0, 0)


@pytest.mark.asyncio
async def test_existing_ticket_deadlines_are_not_rewritten_when_policy_changes():
    from litestar.testing import AsyncTestClient
    from app.main import app
    from app.services import settings_service

    async with AsyncTestClient(app=app) as client:
        customer = await client.post(
            "/api/auth/register",
            json={
                "email": "sla@formtest.com",
                "username": "sla_user",
                "full_name": "Sla User",
                "password": "customerpass123",
            },
        )
        headers = {"Authorization": f"Bearer {customer.json()['access_token']}"}
        created = await client.post(
            "/api/tickets",
            json={"title": "SLA original", "description": "Keep my deadline."},
            headers=headers,
        )
        assert created.status_code in (200, 201), created.text
        original = created.json()["first_response_due_at"]

        await settings_service.set_many({"sla_first_medium": 15, "sla_business_hours_enabled": True})
        fetched = await client.get(f"/api/tickets/{created.json()['id']}", headers=headers)
        assert fetched.json()["first_response_due_at"] == original

    settings_service.invalidate()


def test_timezone_utc_plus_eight():
    # Saturday 10:00 in Asia/Shanghai is Friday 18:00 UTC? 
    # 2026-03-07 02:00 UTC = 2026-03-07 10:00 CST (Saturday).
    start = datetime(2026, 3, 7, 2, 0, 0)
    due = add_business_minutes(start, 15, _policy(sla_timezone="Asia/Shanghai"))
    # Next open: Monday 09:00 Shanghai = Sunday 17:00? Monday 09:00 CST = Monday 01:00 UTC.
    assert due == datetime(2026, 3, 9, 1, 15, 0)
