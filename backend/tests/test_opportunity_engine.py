from lumi.db.session import session_scope
from lumi.services.assistant_suggestions import AssistantSuggestionService
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.worker.jobs import process_due_opportunity_jobs

from .conftest import TEST_TELEGRAM_ID


async def test_due_opportunity_job_precomputes_short_task_suggestion(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        await TaskService(session).create_task(
            u,
            title="Проверить 3 аккаунт почты",
            project="Операции",
            estimated_minutes=5,
        )
        await AssistantSuggestionService(session).enqueue_opportunity(
            u,
            kind="task_suggestions",
            scope_key="today",
            reason="test",
            delay_seconds=0,
        )

    result = await process_due_opportunity_jobs({})
    assert result == "processed 1"

    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        suggestions = await AssistantSuggestionService(session).list_pending(u)
        assert len(suggestions) == 1
        assert suggestions[0].kind == "micro_slot"
        assert suggestions[0].description == "Lumi уже подобрала 1 задачу на 5 мин"
        assert suggestions[0].payload["tasks"][0]["title"] == "Проверить 3 аккаунт почты"
        assert suggestions[0].payload["tasks"][0]["estimated_minutes"] == 5
