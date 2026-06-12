"""Scheduler loop: due scheduled_tasks -> Redis queue.

Every SCHEDULER_TICK_SECONDS:
1. SELECT ... FOR UPDATE SKIP LOCKED due tasks
2. acquire per-row lock (locked_until) to prevent double enqueue
3. create agent_run, enqueue worker job
4. advance next_run_at
"""

from __future__ import annotations

import asyncio
import signal

from lumi.config import get_settings
from lumi.db.session import dispose_engine, session_scope
from lumi.logging import get_logger, setup_logging
from lumi.services.automations import AutomationService
from lumi.services.runs import RunService
from lumi.utils.time import utc_now
from lumi.worker.jobs import AGENT_RUN_TYPE_BY_AUTOMATION, JOB_BY_AUTOMATION_TYPE
from lumi.worker.queue import close_queue, enqueue_job

log = get_logger(__name__)


async def tick() -> int:
    """One scheduler pass. Returns number of enqueued jobs."""
    settings = get_settings()
    enqueued = 0
    async with session_scope() as session:
        automations = AutomationService(session)
        runs = RunService(session)
        due = await automations.find_due_tasks(utc_now())
        for task in due:
            if not automations.try_lock(task, settings.scheduler_lock_seconds):
                continue
            job_name = JOB_BY_AUTOMATION_TYPE.get(task.type.value)
            run_type = AGENT_RUN_TYPE_BY_AUTOMATION.get(task.type.value)
            if not job_name or not run_type:
                log.warning("unknown automation type", fields={"type": task.type.value})
                automations.advance_schedule(task)
                continue
            run = await runs.create(
                user_id=task.user_id,
                type_=run_type,
                trigger="scheduled_task",
                scheduled_task_id=task.id,
                input_summary=task.title,
            )
            job_id = await enqueue_job(
                job_name,
                str(task.user_id),
                agent_run_id=str(run.id),
                scheduled_task_id=str(task.id),
                trigger="scheduled_task",
            )
            if (task.config or {}).get("one_time"):
                task.enabled = False
                task.next_run_at = None
                task.last_run_at = utc_now()
            else:
                automations.advance_schedule(task)
            if job_id:
                enqueued += 1
                log.info(
                    "scheduled job enqueued",
                    fields={"automation": task.title, "job": job_name, "run_id": str(run.id)},
                )
            else:
                automations.mark_failed(task, "queue unavailable")
                await runs.mark_failed(run, "queue unavailable")
    return enqueued


async def run_scheduler() -> None:
    setup_logging()
    settings = get_settings()
    log.info("lumi scheduler started", fields={"tick_seconds": settings.scheduler_tick_seconds})

    stop = asyncio.Event()

    def _request_stop() -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:  # pragma: no cover — non-unix
            pass

    try:
        while not stop.is_set():
            try:
                await tick()
            except Exception:  # noqa: BLE001 — scheduler must survive any tick failure
                log.exception("scheduler tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.scheduler_tick_seconds)
            except TimeoutError:
                pass
    finally:
        await close_queue()
        await dispose_engine()
        log.info("lumi scheduler stopped")


def main() -> None:
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
