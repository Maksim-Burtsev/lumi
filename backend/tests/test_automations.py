from lumi.db.session import session_scope
from lumi.services.automations import AutomationService
from lumi.services.users import UserService

from .conftest import TEST_TELEGRAM_ID


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
