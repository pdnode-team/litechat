"""CSV export of tickets: date range, row cap, formula injection."""
import pytest
from litestar.testing import AsyncTestClient

from app.main import app


async def _staff(client: AsyncTestClient) -> dict:
    res = await client.post(
        "/api/auth/setup-admin",
        json={
            "email": "export-admin@formtest.com",
            "username": "export_admin",
            "full_name": "Export Admin",
            "password": "rootpass123",
        },
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.mark.asyncio
async def test_csv_export_streams_rows_and_quotes_formulas():
    async with AsyncTestClient(app=app) as client:
        headers = await _staff(client)
        customer = await client.post(
            "/api/auth/register",
            json={
                "email": "export-cust@formtest.com",
                "username": "export_cust",
                "full_name": "=HYPERLINK(1)",
                "password": "customerpass123",
            },
        )
        cust_headers = {"Authorization": f"Bearer {customer.json()['access_token']}"}
        created = await client.post(
            "/api/tickets",
            json={"title": "+cmd", "description": "Export me please.", "tags": "@sum"},
            headers=cust_headers,
        )
        assert created.status_code in (200, 201), created.text

        res = await client.get("/api/tickets/export", params={"format": "csv"}, headers=headers)
        assert res.status_code == 200, res.text
        body = res.text
        assert "ticket_code" in body.splitlines()[0]
        assert "'+cmd" in body
        assert "'=HYPERLINK(1)" in body
        assert "'@sum" in body
        assert created.json()["ticket_code"] in body


@pytest.mark.asyncio
async def test_csv_export_rejects_customers():
    async with AsyncTestClient(app=app) as client:
        customer = await client.post(
            "/api/auth/register",
            json={
                "email": "no-export@formtest.com",
                "username": "no_export",
                "full_name": "No Export",
                "password": "customerpass123",
            },
        )
        res = await client.get(
            "/api/tickets/export",
            headers={"Authorization": f"Bearer {customer.json()['access_token']}"},
        )
        assert res.status_code == 403
