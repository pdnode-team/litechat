import os
import pytest
from pathlib import Path

# Force TEST database URL BEFORE importing any app modules
TEST_DB_PATH = Path(__file__).resolve().parent / "test_isolated.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-pytest-execution-only-12345"
# The suite logs in and registers far more often than a real client would; the
# limiter is exercised explicitly in test_rate_limit.py instead.
os.environ["RATE_LIMIT_ENABLED"] = "false"
# Drive the outbox from tests instead of a background loop.
os.environ["EMAIL_OUTBOX_WORKER"] = "false"
os.environ["SLA_WATCH_WORKER"] = "false"

from litestar.testing import AsyncTestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.middleware import limiter  # noqa: E402


@pytest.fixture(autouse=True)
async def setup_test_db():
    limiter.reset()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    limiter.reset()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    # Remove isolated test db file if exists
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink(missing_ok=True)
        except Exception:
            pass
