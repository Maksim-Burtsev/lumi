from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from lumi.db.models import AssistantOpportunityJob, CalendarEvent, CalendarEventStatus, CalendarSource
from lumi.db.session import session_scope
from lumi.llm.base import LLMError
from lumi.services import assistant_suggestions as assistant_suggestions_module
from lumi.services import calendar as calendar_module
from lumi.services.assistant_suggestions import AssistantSuggestionService
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.worker import jobs as jobs_module
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
        assert suggestions[0].description == "Lumi already picked 1 quick win for 5 min"
        assert suggestions[0].payload["tasks"][0]["title"] == "Проверить 3 аккаунт почты"
        assert suggestions[0].payload["tasks"][0]["estimated_minutes"] == 5


async def test_task_changes_enqueue_cleanup_not_slot_refresh(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task = await TaskService(session).create_task(
            u,
            title="Проверить 3 аккаунт почты",
        )

        result = await session.execute(
            select(AssistantOpportunityJob).where(
                AssistantOpportunityJob.user_id == u.id,
                AssistantOpportunityJob.kind == "task_cleanup",
                AssistantOpportunityJob.scope_key == "review",
            )
        )
        job = result.scalar_one()
        assert job.reason == "task.created"
        assert job.payload["task_id"] == str(task.id)


async def test_task_completion_does_not_requeue_cleanup(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task = await TaskService(session).create_task(u, title="Done item")
        await TaskService(session).complete_task(u, task)

        result = await session.execute(
            select(AssistantOpportunityJob).where(
                AssistantOpportunityJob.user_id == u.id,
                AssistantOpportunityJob.kind == "task_cleanup",
                AssistantOpportunityJob.scope_key == "review",
            )
        )
        job = result.scalar_one()
        assert job.reason == "task.created"
        assert job.payload["task_id"] == str(task.id)


async def test_planned_task_missing_optional_fields_needs_no_cleanup(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        await TaskService(session).create_task(
            u,
            title="Planned without project deadline or estimate",
            target_at=datetime.now(UTC) + timedelta(days=1),
        )
        await AssistantSuggestionService(session).enqueue_opportunity(
            u,
            kind="task_cleanup",
            scope_key="review",
            reason="test",
            delay_seconds=0,
        )

    assert await process_due_opportunity_jobs({}) == "processed 0"

    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        assert await AssistantSuggestionService(session).list_pending(u) == []


async def test_task_cleanup_job_creates_structured_llm_decisions(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task = await TaskService(session).create_task(
            u,
            title="Проверить 3 аккаунт почты",
            project="Backlog",
        )
        await AssistantSuggestionService(session).enqueue_opportunity(
            u,
            kind="task_cleanup",
            scope_key="review",
            reason="test",
            delay_seconds=0,
        )

    result = await process_due_opportunity_jobs({})
    assert result == "processed 1"

    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        suggestions = await AssistantSuggestionService(session).list_pending(u, limit=20)
        by_kind = {suggestion.kind: suggestion for suggestion in suggestions}
        assert {"task_estimate", "task_due_date"} <= set(by_kind)
        assert by_kind["task_estimate"].payload["task_id"] == str(task.id)
        assert by_kind["task_estimate"].payload["estimated_minutes"] == 5
        assert by_kind["task_estimate"].payload["source"] == "llm"
        assert by_kind["task_estimate"].payload["confidence"] == "high"
        assert by_kind["task_due_date"].payload["no_deadline"] is True
        assert by_kind["task_due_date"].payload["reason"]


async def test_task_cleanup_job_handles_llm_failure_without_breaking(monkeypatch, user):
    class FailingGateway:
        async def complete_json(self, **kwargs):
            raise LLMError("bad json")

    monkeypatch.setattr(jobs_module, "LLMGateway", lambda: FailingGateway())
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        await TaskService(session).create_task(u, title="Raw backlog idea", project="Backlog")
        await AssistantSuggestionService(session).enqueue_opportunity(
            u,
            kind="task_cleanup",
            scope_key="review",
            reason="test",
            delay_seconds=0,
        )

    result = await process_due_opportunity_jobs({})
    assert result == "processed 0"

    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        assert await AssistantSuggestionService(session).list_pending(u) == []


async def test_task_cleanup_job_allows_limited_controlled_enrichment(monkeypatch, user):
    calls: list[dict] = []

    class EnrichmentGateway:
        async def complete_json(self, **kwargs):
            import json

            payload = json.loads(kwargs["messages"][0].content)
            calls.append(payload)
            if "enrichment" not in payload:
                return {"decisions": [], "enrichment_requests": [{"type": "project", "project": "Lumi"}]}
            task_id = payload["enrichment"][0]["tasks"][0]["id"]
            return {
                "decisions": [{
                    "kind": "task_estimate",
                    "task_id": task_id,
                    "estimated_minutes": 45,
                    "confidence": "medium",
                    "reason": "Comparable project task context.",
                }]
            }

    monkeypatch.setattr(jobs_module, "LLMGateway", lambda: EnrichmentGateway())
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task = await TaskService(session).create_task(u, title="Compare design", project="Lumi")
        task_id = str(task.id)
        await AssistantSuggestionService(session).enqueue_opportunity(
            u,
            kind="task_cleanup",
            scope_key="review",
            reason="test",
            delay_seconds=0,
        )

    result = await process_due_opportunity_jobs({})
    assert result == "processed 1"
    assert len(calls) == 2
    assert calls[1]["enrichment"][0]["request"] == {"type": "project", "project": "Lumi"}

    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        [suggestion] = await AssistantSuggestionService(session).list_pending(u)
        assert suggestion.kind == "task_estimate"
        assert suggestion.payload["task_id"] == task_id


async def test_slot_suggestions_job_creates_micro_slot_with_window(monkeypatch, user):
    now = datetime(2026, 6, 10, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(jobs_module, "utc_now", lambda: now)
    monkeypatch.setattr(calendar_module, "utc_now", lambda: now)
    monkeypatch.setattr(assistant_suggestions_module, "utc_now", lambda: now)
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        session.add(
            CalendarEvent(
                user_id=u.id,
                title="Busy meeting",
                start_at=now + timedelta(hours=1),
                end_at=now + timedelta(hours=2),
                timezone=u.timezone,
                all_day=False,
                busy=True,
                status=CalendarEventStatus.CONFIRMED,
                source=CalendarSource.INTERNAL,
                created_by="user",
            )
        )
        await TaskService(session).create_task(
            u,
            title="Проверить 3 аккаунт почты",
            project="Операции",
            estimated_minutes=5,
        )
        await AssistantSuggestionService(session).enqueue_opportunity(
            u,
            kind="slot_suggestions",
            scope_key="today",
            reason="test",
            payload={"date": "2026-06-10"},
            delay_seconds=0,
        )

    result = await process_due_opportunity_jobs({})
    assert result == "processed 1"

    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        [suggestion] = await AssistantSuggestionService(session).list_pending(u)
        assert suggestion.kind == "micro_slot"
        assert suggestion.payload["slot"]["start_at"] < suggestion.payload["slot"]["end_at"]
        assert suggestion.payload["reason"]
        assert suggestion.payload["source"] in {"llm", "heuristic"}
        assert suggestion.payload["tasks"][0]["title"] == "Проверить 3 аккаунт почты"


async def test_active_user_sweep_queues_cleanup_only_for_recent_users(user):
    async with session_scope() as session:
        recent = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        recent.last_seen_at = datetime.now(UTC)
        stale = await UserService(session).ensure_user(777001, first_name="Stale")
        stale.last_seen_at = datetime.now(UTC) - timedelta(days=2)

    result = await jobs_module.enqueue_active_user_task_cleanup({})
    assert result == "queued 1"

    async with session_scope() as session:
        result = await session.execute(select(AssistantOpportunityJob))
        jobs = list(result.scalars())
        assert len(jobs) == 1
        assert jobs[0].user_id == recent.id
        assert jobs[0].kind == "task_cleanup"


async def test_daily_task_cleanup_uses_user_timezone_workday_start(monkeypatch, user):
    now = datetime(2026, 6, 10, 10, 5, tzinfo=UTC)  # 14:05 in Asia/Yerevan.
    monkeypatch.setattr(jobs_module, "utc_now", lambda: now)
    async with session_scope() as session:
        local_start_user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        local_start_user.timezone = "Asia/Yerevan"
        local_start_user.last_seen_at = now
        local_start_user.settings = {
            **(local_start_user.settings or {}),
            "planning": {"work_hours": {"start": "14:00", "end": "19:00"}},
        }
        expected_user_id = local_start_user.id
        wrong_hour_user = await UserService(session).ensure_user(777001, first_name="Wrong hour")
        wrong_hour_user.timezone = "UTC"
        wrong_hour_user.last_seen_at = now
        wrong_hour_user.settings = {
            **(wrong_hour_user.settings or {}),
            "planning": {"work_hours": {"start": "09:00", "end": "17:00"}},
        }

    result = await jobs_module.enqueue_daily_task_cleanup({})
    assert result == "queued 1"

    async with session_scope() as session:
        result = await session.execute(select(AssistantOpportunityJob))
        [job] = list(result.scalars())
        assert job.user_id == expected_user_id
        assert job.kind == "task_cleanup"
        assert job.scope_key == "daily:2026-06-10"
