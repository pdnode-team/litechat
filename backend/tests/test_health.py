"""Health probe and optional 5xx webhook."""
from unittest.mock import MagicMock

import pytest
from litestar.testing import AsyncTestClient

import app.main as main_module
from app.exception_handlers import server_error_handler
from app.main import app


@pytest.mark.asyncio
async def test_health_reports_ok_when_database_answers():
    async with AsyncTestClient(app=app) as client:
        res = await client.get("/api/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["service"] == "LiteChat"
        assert body["database"] == "ok"


@pytest.mark.asyncio
async def test_health_is_503_when_database_fails(monkeypatch):
    class BoomSession:
        async def execute(self, *args, **kwargs):
            raise RuntimeError("database unreachable")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(main_module, "async_session_factory", lambda: BoomSession())

    async with AsyncTestClient(app=app) as client:
        res = await client.get("/api/health")
        assert res.status_code == 503
        body = res.json()
        assert body["status"] == "degraded"
        assert body["database"] == "error"


def test_server_error_handler_schedules_alert_without_failing(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr("app.services.alerts.schedule_alert", captured.append)

    request = MagicMock()
    request.method = "GET"
    request.url.path = "/api/tickets"
    request.url.query = ""
    request.headers.get.return_value = "pytest"
    request.scope = {"client": ("127.0.0.1", 9)}

    response = server_error_handler(request, RuntimeError("boom"))
    assert response.status_code == 500
    assert captured
    payload = captured[0]
    assert payload["event"] == "server_error"
    assert payload["path"] == "/api/tickets"
    assert "boom" in payload["exception"]


def test_alert_failure_does_not_change_the_500(monkeypatch):
    def explode(_payload):
        raise RuntimeError("webhook down")

    monkeypatch.setattr("app.services.alerts.schedule_alert", explode)

    request = MagicMock()
    request.method = "POST"
    request.url.path = "/api/auth/login"
    request.url.query = ""
    request.headers.get.return_value = "-"
    request.scope = {}

    response = server_error_handler(request, RuntimeError("original"))
    assert response.status_code == 500
    detail = str(response.content.get("detail", ""))
    assert "original" in detail or "reference" in detail.lower()
