"""Explicit local-only demo data for Focus Sessions.

Run: python -m lumi.scripts.seed_focus_demo

The script replaces only rows carrying its stable ``seed_batch_id``. It never
deletes records by matching user-visible text.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

from sqlalchemy import delete, select

from lumi.config import get_settings
from lumi.db.models import (
    CalendarEvent,
    FocusSession,
    FocusSessionStatus,
    Task,
    TaskEvent,
    TaskStatus,
)
from lumi.db.session import dispose_engine, session_scope
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.utils.time import get_zone, utc_now

FOCUS_DEMO_SEED_BATCH_ID = uuid.UUID("f0c05eed-2026-4000-8000-000000000001")

SEED_TASKS = [
    ("Write product spec", "Lumi", ["focus", "product"], TaskStatus.ACTIVE),
    ("Focus timer v2 QA", "Lumi", ["qa", "miniapp"], TaskStatus.ACTIVE),
    ("Polish breathing orb", "Lumi", ["ui", "timer"], TaskStatus.ACTIVE),
    ("Design analytics grid", "Lumi", ["analytics", "ui"], TaskStatus.ACTIVE),
    ("QA task search project", "QA Project", ["qa"], TaskStatus.ACTIVE),
    ("Regression checklist", "QA Project", ["qa", "release"], TaskStatus.ACTIVE),
    ("Mobile layout pass", "QA Project", ["mobile"], TaskStatus.INBOX),
    ("Manual log regression", "Manual QA", ["manual", "focus"], TaskStatus.INBOX),
    ("Reflection form QA", "Manual QA", ["manual", "reflection"], TaskStatus.ACTIVE),
    ("Prepare analytics review", "Ops Review", ["analytics"], TaskStatus.ACTIVE),
    ("Weekly status notes", "Ops Review", ["status"], TaskStatus.ACTIVE),
    ("Triage follow-ups", "Ops Review", ["ops"], TaskStatus.INBOX),
    ("Draft reflection prompts", "AI Coach", ["reflection"], TaskStatus.INBOX),
    ("LLM insight prompt", "AI Coach", ["llm", "analytics"], TaskStatus.ACTIVE),
    ("Summarize focus patterns", "AI Coach", ["llm", "review"], TaskStatus.ACTIVE),
    ("Calendar focus blocks", "Calendar", ["calendar", "planning"], TaskStatus.ACTIVE),
    ("Morning planning flow", "Calendar", ["planning"], TaskStatus.INBOX),
    ("Yandex sync review", "Calendar", ["sync"], TaskStatus.ACTIVE),
    ("Inbox capture cleanup", "Inbox Zero", ["inbox"], TaskStatus.INBOX),
    ("Email triage design", "Inbox Zero", ["email"], TaskStatus.ACTIVE),
    ("Notification copy pass", "Inbox Zero", ["copy"], TaskStatus.ACTIVE),
    ("Launch notes draft", "Release", ["release"], TaskStatus.ACTIVE),
    ("PR checklist update", "Release", ["github"], TaskStatus.INBOX),
    ("Screenshots for PR", "Release", ["qa", "screens"], TaskStatus.ACTIVE),
]


async def seed() -> None:
    settings = get_settings()
    if not settings.is_local:
        raise RuntimeError("focus demo seed is allowed only when APP_ENV=local")
    if not settings.allowed_telegram_user_ids:
        print("ALLOWED_TELEGRAM_USER_IDS пуст — ничего не создано.")
        return

    telegram_user_id = settings.allowed_telegram_user_ids[0]
    async with session_scope() as session:
        user_service = UserService(session)
        user = await user_service.ensure_user(telegram_user_id)
        await user_service.ensure_main_conversation(user)
        await session.execute(
            delete(FocusSession).where(
                FocusSession.user_id == user.id,
                FocusSession.seed_batch_id == FOCUS_DEMO_SEED_BATCH_ID,
            )
        )

        # Remove tasks that disappeared from this seed version, but only when the
        # marker proves this script created them and no user-owned record now links
        # to them. Unmarked rows are never selected, even if their source/title match.
        seed_titles = {title for title, *_ in SEED_TASKS}
        stale_tasks = list(
            (
                await session.execute(
                    select(Task).where(
                        Task.user_id == user.id,
                        Task.source == "seed_focus_demo",
                        Task.metadata_["seed_batch_id"].astext == str(FOCUS_DEMO_SEED_BATCH_ID),
                        Task.title.not_in(seed_titles),
                    )
                )
            ).scalars()
        )
        tasks_removed = 0
        for stale_task in stale_tasks:
            linked_focus = await session.scalar(
                select(FocusSession.id).where(FocusSession.task_id == stale_task.id).limit(1)
            )
            linked_calendar = await session.scalar(
                select(CalendarEvent.id).where(CalendarEvent.source_task_id == stale_task.id).limit(1)
            )
            if linked_focus is not None or linked_calendar is not None:
                continue
            await session.execute(delete(TaskEvent).where(TaskEvent.task_id == stale_task.id))
            await session.delete(stale_task)
            tasks_removed += 1

        task_service = TaskService(session)
        task_by_title: dict[str, Task] = {}
        task_created = 0
        for title, project_name, tags, status in SEED_TASKS:
            existing = await session.scalar(
                select(Task)
                .where(
                    Task.user_id == user.id,
                    Task.source == "seed_focus_demo",
                    Task.metadata_["seed_batch_id"].astext == str(FOCUS_DEMO_SEED_BATCH_ID),
                    Task.title == title,
                )
                .limit(1)
            )
            if existing is None:
                existing = await task_service.create_task(
                    user,
                    title=title,
                    project=project_name,
                    tags=tags,
                    source="seed_focus_demo",
                    created_by="system",
                    actor="system",
                )
                existing.metadata_ = {
                    **(existing.metadata_ or {}),
                    "seed_batch_id": str(FOCUS_DEMO_SEED_BATCH_ID),
                }
                task_created += 1
            existing.status = status
            task_by_title[title] = existing

        zone = get_zone(user.timezone)
        today = utc_now().astimezone(zone).replace(hour=9, minute=0, second=0, microsecond=0)
        task_options = [*task_by_title.values(), None]
        intentions = [
            "Write product spec",
            "Review implementation plan",
            "Polish breathing orb",
            "QA timer finish flow",
            "Design analytics grid",
            "Manual regression pass",
            "Prepare release notes",
            "Triage inbox follow-ups",
            "Calendar sync review",
            "Draft reflection prompts",
            "Summarize focus patterns",
            "Mobile layout pass",
        ]
        results = [
            "Moved the feature forward and captured follow-up notes.",
            "Validated the core flow and logged edge cases.",
            "Cleaned up UI details and checked responsive behavior.",
            "Reviewed the data model and tested the important path.",
            "Finished the planned chunk without major blockers.",
        ]
        next_steps = [
            "Run browser QA.",
            "Tighten copy.",
            "Check mobile layout.",
            "Update PR notes.",
            "Review analytics after more data.",
        ]
        durations = [18, 22, 25, 32, 39, 45, 50, 55, 65, 75, 90]
        hours = [6, 7, 9, 10, 11, 13, 15, 17, 19, 21, 23]
        for index in range(100):
            task = task_options[index % len(task_options)]
            started_local = (today - timedelta(days=index % 30)).replace(
                hour=hours[(index * 7) % len(hours)],
                minute=(index * 11) % 50,
            )
            started = started_local.astimezone(utc_now().tzinfo)
            minutes = durations[(index * 5) % len(durations)]
            session.add(
                FocusSession(
                    user_id=user.id,
                    task_id=task.id if task else None,
                    project_id=task.project_id if task else None,
                    project_snapshot=task.project if task else None,
                    intention=intentions[index % len(intentions)],
                    planned_minutes=minutes,
                    status=FocusSessionStatus.COMPLETED,
                    started_at=started,
                    target_end_at=started + timedelta(minutes=minutes),
                    ended_at=started + timedelta(minutes=minutes),
                    duration_seconds=minutes * 60,
                    accomplished_text=results[index % len(results)],
                    next_step_text=next_steps[index % len(next_steps)],
                    focus_score=3 + (index % 3),
                    seed_batch_id=FOCUS_DEMO_SEED_BATCH_ID,
                )
            )

    print(
        "Focus demo seed готов: "
        f"batch={FOCUS_DEMO_SEED_BATCH_ID}, tasks_created={task_created}, "
        f"tasks_removed={tasks_removed}, sessions=100"
    )
    await dispose_engine()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
