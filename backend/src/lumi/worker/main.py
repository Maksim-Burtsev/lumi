"""arq worker entrypoint: `python -m lumi.worker.main`."""

from __future__ import annotations

from typing import Any

from arq import cron, run_worker

from lumi.config import get_settings
from lumi.logging import get_logger, setup_logging
from lumi.worker.jobs import (
    cleanup_ui_events,
    compact_conversation,
    enqueue_active_user_task_cleanup,
    enqueue_daily_task_cleanup,
    enqueue_due_assistant_turns,
    process_assistant_turn,
    process_due_opportunity_jobs,
    recover_pending_calendar_private_note_summaries,
    run_calendar_sync,
    run_daily_planning,
    send_due_reminders,
    summarize_calendar_private_note,
)
from lumi.worker.queue import redis_settings

log = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    setup_logging()
    log.info("lumi worker started")


async def shutdown(ctx: dict[str, Any]) -> None:
    from lumi.db.session import dispose_engine

    await dispose_engine()
    log.info("lumi worker stopped")


class WorkerSettings:
    functions = [
        run_daily_planning,
        run_calendar_sync,
        summarize_calendar_private_note,
        compact_conversation,
        process_assistant_turn,
        process_due_opportunity_jobs,
        enqueue_active_user_task_cleanup,
        enqueue_daily_task_cleanup,
        cleanup_ui_events,
    ]
    cron_jobs = [
        # Reminder delivery: every minute.
        cron(send_due_reminders, second=15, unique=True),
        # Recovery for saved chat turns when enqueue failed or a process restarted.
        cron(enqueue_due_assistant_turns, second=45, unique=True),
        # Low-latency proactive task/project opportunities.
        cron(process_due_opportunity_jobs, second=35, unique=True),
        cron(enqueue_active_user_task_cleanup, minute={0, 15, 30, 45}, second=25, unique=True),
        cron(enqueue_daily_task_cleanup, minute=5, second=5, unique=True),
        # Realtime outbox retention: durable catch-up is 72h.
        cron(cleanup_ui_events, hour=3, minute=20, unique=True),
        cron(recover_pending_calendar_private_note_summaries, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}, unique=True),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings()
    max_jobs = get_settings().worker_max_jobs
    job_timeout = 600
    keep_result = 3600


def main() -> None:
    run_worker(WorkerSettings)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
