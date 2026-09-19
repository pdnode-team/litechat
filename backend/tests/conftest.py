import os
import pytest
from pathlib import Path

# Force TEST database URL BEFORE importing any app modules
TEST_DB_PATH = Path(__file__).resolve().parent / "test_isolated.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-pytest-execution-only-12345"

from litestar.testing import AsyncTestClient
from app.main import app
from app.db.base import Base
from app.db.session import engine

@pytest.fixture(autouse=True)
async def setup_test_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    # Remove isolated test db file if exists
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink(missing_ok=True)
        except Exception:
            pass
