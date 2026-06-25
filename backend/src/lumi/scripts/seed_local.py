"""Seed: user, main conversation, default news topics, default automations.

Run: python -m lumi.scripts.seed_local
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select

from lumi.config import get_settings
from lumi.db.models import FocusSession, FocusSessionStatus, Task, TaskStatus
from lumi.db.session import dispose_engine, session_scope
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.utils.time import get_zone, utc_now

# Automations and news topics are user-created in the Mini App — no defaults on purpose.


async def seed() -> None:
    settings = get_settings()
    if not settings.allowed_telegram_user_ids:
        print("ALLOWED_TELEGRAM_USER_IDS пуст — заполни .env и повтори. Ничего не создано.")
        return

    telegram_user_id = settings.allowed_telegram_user_ids[0]
    created: list[str] = []

    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(telegram_user_id)
        await users.ensure_main_conversation(user)
        tasks = TaskService(session)
        created.append(f"user telegram_id={telegram_user_id}")
        created.append("main conversation")

        seed_tasks = [
            {"title": "Write product spec", "project": "Lumi", "tags": ["focus", "product"], "status": TaskStatus.ACTIVE},
            {"title": "Focus timer v2 QA", "project": "Lumi", "tags": ["qa", "miniapp"], "status": TaskStatus.ACTIVE},
            {"title": "QA task search project", "project": "QA Project", "tags": ["qa"], "status": TaskStatus.ACTIVE},
            {"title": "Manual log regression", "project": "Manual QA", "tags": ["manual", "focus"], "status": TaskStatus.INBOX},
            {"title": "Prepare analytics review", "project": "Ops Review", "tags": ["analytics"], "status": TaskStatus.ACTIVE},
            {"title": "Draft reflection prompts", "project": "AI Coach", "tags": ["reflection"], "status": TaskStatus.INBOX},
        ]
        task_by_title: dict[str, Task] = {}
        task_created = 0
        for item in seed_tasks:
            existing = await session.scalar(
                select(Task).where(Task.user_id == user.id, Task.title == item["title"]).limit(1)
            )
            if existing is None:
                existing = await tasks.create_task(
                    user,
                    title=item["title"],
                    project=item["project"],
                    tags=item["tags"],
                    source="seed_local",
                    created_by="system",
                    actor="system",
                )
                existing.status = item["status"]
                task_created += 1
            task_by_title[existing.title] = existing

        zone = get_zone(user.timezone)
        today = utc_now().astimezone(zone).replace(hour=10, minute=0, second=0, microsecond=0)
        focus_seed = [
            (-6, "Plan Sessions v2", "Lumi", "Write product spec", 50, 5, "Outlined active mode and details sheet.", "Keep orb simple."),
            (-5, "QA manual log", "Manual QA", "Manual log regression", 32, 4, "Checked date/time inputs and custom duration.", "Retest project override."),
            (-4, "Task picker cleanup", "QA Project", "QA task search project", 39, 4, "Validated search by title and project.", "Add scroll evidence."),
            (-3, "Analytics pass", "Ops Review", "Prepare analytics review", 65, 5, "Reviewed weekly split and project totals.", "Tune empty days."),
            (-2, "Reflection prompts", "AI Coach", "Draft reflection prompts", 28, 3, "Drafted reflection questions.", "Shorten copy."),
            (-1, "No-project focus block", None, None, 18, 4, "Handled quick maintenance without project.", "File follow-up task."),
            (0, "Polish breathing orb", "Lumi", "Focus timer v2 QA", 45, 5, "Matched selected active-session mock.", "Run mobile QA."),
        ]
        session_created = 0
        for offset, intention, project, task_title, minutes, score, done, next_step in focus_seed:
            started = today + timedelta(days=offset, hours=offset % 3)
            started_utc = started.astimezone(utc_now().tzinfo)
            exists = await session.scalar(
                select(FocusSession)
                .where(
                    FocusSession.user_id == user.id,
                    FocusSession.intention == intention,
                    FocusSession.started_at == started_utc,
                )
                .limit(1)
            )
            if exists is not None:
                continue
            task = task_by_title.get(task_title or "")
            focus_session = FocusSession(
                user_id=user.id,
                task_id=task.id if task else None,
                project_snapshot=project,
                intention=intention,
                planned_minutes=minutes,
                status=FocusSessionStatus.COMPLETED,
                started_at=started_utc,
                target_end_at=started_utc + timedelta(minutes=minutes),
                ended_at=started_utc + timedelta(minutes=minutes),
                duration_seconds=minutes * 60,
                accomplished_text=done,
                distraction_text=None,
                next_step_text=next_step,
                focus_score=score,
            )
            session.add(focus_session)
            session_created += 1

        created.append(f"focus tasks created={task_created}")
        created.append(f"focus sessions created={session_created}")

    print("Seed готов. Создано/проверено:")
    for line in created:
        print(f"  • {line}")
    await dispose_engine()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
