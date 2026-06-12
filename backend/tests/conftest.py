"""Test fixtures: isolated lumi_test database, clean tables per test."""

from __future__ import annotations

import os

# --- Environment must be configured BEFORE any lumi import -------------------
_base_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://lumi:lumi@localhost:5432/lumi")
_base_db_name = _base_url.rsplit("/", 1)[1].split("?")[0]
TEST_DATABASE_URL = _base_url.rsplit("/", 1)[0] + "/lumi_test"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["LLM_PROVIDER"] = "mock"
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456789:TEST-TOKEN-for-tests-only")
os.environ.setdefault("ALLOWED_TELEGRAM_USER_IDS", "777000")
os.environ["APP_ENV"] = "local"
os.environ["DEV_AUTH_ENABLED"] = "false"
os.environ["AUTO_MIGRATE"] = "false"

import pytest  # noqa: E402

from lumi.db.base import Base  # noqa: E402
from lumi.db.session import dispose_engine, get_engine, session_scope  # noqa: E402
from lumi.llm.gateway import reset_llm_provider  # noqa: E402
from lumi.services.users import UserService  # noqa: E402

_schema_ready = False


async def _ensure_test_database() -> None:
    """Create the lumi_test database if missing (idempotent)."""
    import asyncpg

    dsn = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    admin_dsn = dsn.rsplit("/", 1)[0] + f"/{_base_db_name}"
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute("CREATE DATABASE lumi_test")
    except asyncpg.DuplicateDatabaseError:
        pass
    finally:
        await conn.close()


@pytest.fixture(autouse=True)
async def clean_db():
    """Fresh schema + empty tables for every test; engine disposed afterwards."""
    global _schema_ready
    await _ensure_test_database()
    engine = get_engine()
    async with engine.begin() as conn:
        if not _schema_ready:
            await conn.run_sync(Base.metadata.create_all)
            _schema_ready = True
        table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        from sqlalchemy import text

        await conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
    reset_llm_provider()
    yield
    await dispose_engine()


TEST_TELEGRAM_ID = 777000


@pytest.fixture
async def user():
    async with session_scope() as session:
        service = UserService(session)
        user = await service.ensure_user(TEST_TELEGRAM_ID, first_name="Тест", username="tester")
        await service.ensure_main_conversation(user)
    return user


@pytest.fixture
async def db_session():
    async with session_scope() as session:
        yield session
