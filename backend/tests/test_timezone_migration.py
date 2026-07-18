from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select

from lumi.db.models import CalendarEvent, CalendarSource, ScheduledTask
from lumi.services.automations import AutomationService
from lumi.services.users import UserService
from lumi.utils.time import local_to_utc

from .conftest import TEST_TELEGRAM_ID


def _load_timezone_migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "7c2d9a0f4b1a_cleanup_invalid_timezones.py"
    )
    spec = importlib.util.spec_from_file_location("timezone_cleanup_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_alembic_has_single_head():
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))

    assert ScriptDirectory.from_config(config).get_heads() == ["a4c8d2e71f6b"]


async def test_timezone_cleanup_migration_repairs_invalid_user_task_and_event(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    user.timezone = "Asia/Yerevan"
    task = await AutomationService(db_session).ensure_system_calendar_sync(user)
    event = CalendarEvent(
        user_id=user.id,
        source=CalendarSource.INTERNAL,
        title="Focus",
        start_at=local_to_utc(__import__("datetime").datetime(2026, 6, 17, 10, 0), user.timezone),
        end_at=local_to_utc(__import__("datetime").datetime(2026, 6, 17, 11, 0), user.timezone),
        timezone="Mars/Olympus",
    )
    db_session.add(event)
    await db_session.flush()

    user.timezone = "Mars/Olympus"
    task.timezone = "Mars/Olympus"
    before_next_run_at = task.next_run_at
    await db_session.flush()

    migration = _load_timezone_migration()
    await db_session.run_sync(lambda sync_session: migration.cleanup_invalid_timezones(sync_session.connection()))
    await db_session.refresh(user)
    await db_session.refresh(task)
    await db_session.refresh(event)

    assert user.timezone == "Europe/Moscow"
    assert task.timezone == "Europe/Moscow"
    assert task.next_run_at is not None
    assert task.next_run_at >= before_next_run_at
    assert event.timezone == "Europe/Moscow"

    stored_task = await db_session.scalar(select(ScheduledTask).where(ScheduledTask.id == task.id))
    assert stored_task.timezone == "Europe/Moscow"
