"""arq worker entrypoint: `python -m lumi.worker.main`."""

from __future__ import annotations

from typing import Any

from arq import cron, run_worker

from lumi.config import get_settings
from lumi.logging import get_logger, setup_logging
from lumi.worker.jobs import (
    compact_conversation,
    enqueue_due_assistant_turns,
    process_assistant_turn,
    run_calendar_sync,
    run_custom_prompt,
    run_daily_planning,
    run_email_triage,
    run_morning_brief,
    run_news_digest,
    run_task_review,
    send_due_reminders,
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
        run_morning_brief,
        run_news_digest,
        run_email_triage,
        run_daily_planning,
        run_calendar_sync,
        run_task_review,
        run_custom_prompt,
        compact_conversation,
        process_assistant_turn,
    ]
    cron_jobs = [
        # Reminder delivery: every minute.
        cron(send_due_reminders, second=15, unique=True),
        # Recovery for saved chat turns when enqueue failed or a process restarted.
        cron(enqueue_due_assistant_turns, second=45, unique=True),
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
