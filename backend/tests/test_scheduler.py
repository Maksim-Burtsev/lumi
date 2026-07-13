from sqlalchemy import select

from lumi.db.models import AgentRun, ScheduledTask, ScheduledTaskType
from lumi.db.session import session_scope
from lumi.scheduler import main as scheduler_main
from lumi.services.automations import AutomationService
from lumi.services.users import UserService
from lumi.utils.time import utc_now

from .conftest import TEST_TELEGRAM_ID


async def test_system_calendar_sync_runs_without_user_notification(user, monkeypatch):
    enqueued: list[dict] = []

    async def fake_enqueue_job(job_name, user_id, **kwargs):
        enqueued.append({"job_name": job_name, "user_id": user_id, **kwargs})
        return "job-id"

    monkeypatch.setattr(scheduler_main, "enqueue_job", fake_enqueue_job)

    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task = await AutomationService(session).ensure_system_calendar_sync(u)
        task.next_run_at = utc_now()

    assert await scheduler_main.tick() == 1
    assert enqueued[0]["job_name"] == "run_calendar_sync"
    assert enqueued[0]["notify"] is False


async def test_legacy_user_scheduled_rows_are_disabled_without_enqueue(user, monkeypatch):
    enqueued: list[dict] = []

    async def fake_enqueue_job(job_name, user_id, **kwargs):
        enqueued.append({"job_name": job_name, "user_id": user_id, **kwargs})
        return "job-id"

    monkeypatch.setattr(scheduler_main, "enqueue_job", fake_enqueue_job)
    legacy_types = (
        ScheduledTaskType.MORNING_BRIEF,
        ScheduledTaskType.NEWS_DIGEST,
        ScheduledTaskType.EMAIL_TRIAGE,
        ScheduledTaskType.DAILY_PLANNING,
        ScheduledTaskType.TASK_REVIEW,
        ScheduledTaskType.CUSTOM_PROMPT,
    )
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        for task_type in legacy_types:
            session.add(
                ScheduledTask(
                    user_id=u.id,
                    type=task_type,
                    title=f"legacy {task_type.value}",
                    cron_expression="* * * * *",
                    timezone=u.timezone,
                    config={},
                    enabled=True,
                    next_run_at=utc_now(),
                )
            )

    assert await scheduler_main.tick() == 0
    assert enqueued == []

    async with session_scope() as session:
        rows = list((await session.execute(select(ScheduledTask))).scalars())
        runs = list((await session.execute(select(AgentRun))).scalars())
        assert len(rows) == len(legacy_types)
        assert runs == []
        for row in rows:
            assert row.enabled is False
            assert row.next_run_at is None
            assert row.locked_until is None
            assert row.last_error == "disabled: removed from product scope"
