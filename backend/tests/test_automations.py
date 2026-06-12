import pytest

from lumi.db.session import session_scope
from lumi.services.automations import AutomationService
from lumi.services.users import UserService
from lumi.utils.time import utc_now

from .conftest import TEST_TELEGRAM_ID


async def test_create_computes_next_run(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = AutomationService(session)
        automation = await service.create(
            u, type_="news_digest", title="Утро", cron_expression="30 8 * * 1-5"
        )
        assert automation.next_run_at is not None
        assert automation.next_run_at > utc_now()


async def test_invalid_cron_rejected(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        with pytest.raises(ValueError):
            await AutomationService(session).create(
                u, type_="news_digest", title="x", cron_expression="не крон"
            )


async def test_due_and_lock(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = AutomationService(session)
        due_task = await service.create(
            u, type_="news_digest", title="due", cron_expression="* * * * *"
        )
        due_task.next_run_at = utc_now()
        disabled = await service.create(
            u, type_="email_triage", title="off", cron_expression="* * * * *", enabled=False
        )
        disabled.next_run_at = utc_now()
        await session.flush()

        due = await service.find_due_tasks()
        ids = [t.id for t in due]
        assert due_task.id in ids
        assert disabled.id not in ids

        # Lock prevents a second enqueue within the lock window.
        assert service.try_lock(due_task, lock_seconds=300) is True
        assert service.try_lock(due_task, lock_seconds=300) is False

        before = due_task.next_run_at
        service.advance_schedule(due_task)
        assert due_task.last_run_at is not None
        assert due_task.next_run_at > before


async def test_disable_clears_next_run(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = AutomationService(session)
        automation = await service.create(
            u, type_="daily_planning", title="План", cron_expression="45 8 * * 1-5"
        )
        automation = await service.update(u, automation, {"enabled": False})
        assert automation.enabled is False
        assert automation.next_run_at is None


async def test_system_calendar_sync_is_hidden_from_user_automations(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = AutomationService(session)

        system_task = await service.ensure_system_calendar_sync(u)
        again = await service.ensure_system_calendar_sync(u)

        assert again.id == system_task.id
        assert system_task.enabled is True
        assert system_task.cron_expression == "*/5 * * * *"
        assert system_task.config["system"] is True
        assert system_task.next_run_at is not None
        assert await service.list_for_user(u) == []
        assert [task.id for task in await service.list_for_user(u, include_system=True)] == [
            system_task.id
        ]
