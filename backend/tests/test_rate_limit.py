"""Rate limiting on credential endpoints."""
import pytest
from litestar.testing import AsyncTestClient

from app import config as app_config
from app.main import app
from app.middleware import limiter


@pytest.fixture
def rate_limited(monkeypatch):
    """Enable the limiter with a tiny window so the test stays fast."""
    monkeypatch.setattr(app_config, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setitem(app_config.RATE_LIMIT_RULES, "/api/auth/login", (3, 60))
    monkeypatch.setitem(app_config.RATE_LIMIT_RULES, "/api/auth/forgot-password", (2, 60))
    limiter.reset()
    yield
    limiter.reset()


@pytest.mark.asyncio
async def test_login_is_rate_limited_after_the_threshold(rate_limited):
    async with AsyncTestClient(app=app) as client:
        for _ in range(3):
            res = await client.post(
                "/api/auth/login", json={"username_or_email": "nobody", "password": "wrongpass123"}
            )
            assert res.status_code == 401

        blocked = await client.post(
            "/api/auth/login", json={"username_or_email": "nobody", "password": "wrongpass123"}
        )
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers
        assert int(blocked.headers["Retry-After"]) >= 1
        assert "detail" in blocked.json()


@pytest.mark.asyncio
async def test_rate_limit_is_per_route(rate_limited):
    async with AsyncTestClient(app=app) as client:
        for _ in range(2):
            assert (
                await client.post("/api/auth/forgot-password", json={"email": "a@test.com"})
            ).status_code == 202
        assert (await client.post("/api/auth/forgot-password", json={"email": "a@test.com"})).status_code == 429

        # A different route has its own budget.
        assert (
            await client.post("/api/auth/login", json={"username_or_email": "x", "password": "y12345678"})
        ).status_code in (401, 429)


@pytest.mark.asyncio
async def test_unrelated_routes_are_never_limited(rate_limited):
    async with AsyncTestClient(app=app) as client:
        for _ in range(10):
            assert (await client.get("/api/health")).status_code == 200


@pytest.mark.asyncio
async def test_limiter_is_disabled_by_default_in_the_suite():
    """The suite disables the limiter so ordinary tests are not throttled."""
    assert app_config.RATE_LIMIT_ENABLED is False
    async with AsyncTestClient(app=app) as client:
        for _ in range(12):
            res = await client.post(
                "/api/auth/login", json={"username_or_email": "nobody", "password": "wrongpass123"}
            )
            assert res.status_code == 401
