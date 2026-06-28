"""Seed: user, main conversation, default news topics, default automations.

Run: python -m lumi.scripts.seed_local
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import delete, select

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
            {"title": "Polish breathing orb", "project": "Lumi", "tags": ["ui", "timer"], "status": TaskStatus.ACTIVE},
            {"title": "Design analytics grid", "project": "Lumi", "tags": ["analytics", "ui"], "status": TaskStatus.ACTIVE},
            {"title": "QA task search project", "project": "QA Project", "tags": ["qa"], "status": TaskStatus.ACTIVE},
            {"title": "Regression checklist", "project": "QA Project", "tags": ["qa", "release"], "status": TaskStatus.ACTIVE},
            {"title": "Mobile layout pass", "project": "QA Project", "tags": ["mobile"], "status": TaskStatus.INBOX},
            {"title": "Manual log regression", "project": "Manual QA", "tags": ["manual", "focus"], "status": TaskStatus.INBOX},
            {"title": "Reflection form QA", "project": "Manual QA", "tags": ["manual", "reflection"], "status": TaskStatus.ACTIVE},
            {"title": "Prepare analytics review", "project": "Ops Review", "tags": ["analytics"], "status": TaskStatus.ACTIVE},
            {"title": "Weekly status notes", "project": "Ops Review", "tags": ["status"], "status": TaskStatus.ACTIVE},
            {"title": "Triage follow-ups", "project": "Ops Review", "tags": ["ops"], "status": TaskStatus.INBOX},
            {"title": "Draft reflection prompts", "project": "AI Coach", "tags": ["reflection"], "status": TaskStatus.INBOX},
            {"title": "LLM insight prompt", "project": "AI Coach", "tags": ["llm", "analytics"], "status": TaskStatus.ACTIVE},
            {"title": "Summarize focus patterns", "project": "AI Coach", "tags": ["llm", "review"], "status": TaskStatus.ACTIVE},
            {"title": "Calendar focus blocks", "project": "Calendar", "tags": ["calendar", "planning"], "status": TaskStatus.ACTIVE},
            {"title": "Morning planning flow", "project": "Calendar", "tags": ["planning"], "status": TaskStatus.INBOX},
            {"title": "Yandex sync review", "project": "Calendar", "tags": ["sync"], "status": TaskStatus.ACTIVE},
            {"title": "Inbox capture cleanup", "project": "Inbox Zero", "tags": ["inbox"], "status": TaskStatus.INBOX},
            {"title": "Email triage design", "project": "Inbox Zero", "tags": ["email"], "status": TaskStatus.ACTIVE},
            {"title": "Notification copy pass", "project": "Inbox Zero", "tags": ["copy"], "status": TaskStatus.ACTIVE},
            {"title": "Launch notes draft", "project": "Release", "tags": ["release"], "status": TaskStatus.ACTIVE},
            {"title": "PR checklist update", "project": "Release", "tags": ["github"], "status": TaskStatus.INBOX},
            {"title": "Screenshots for PR", "project": "Release", "tags": ["qa", "screens"], "status": TaskStatus.ACTIVE},
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
        today = utc_now().astimezone(zone).replace(hour=9, minute=0, second=0, microsecond=0)
        project_tasks = [
            ("Lumi", "Write product spec"),
            ("Lumi", "Focus timer v2 QA"),
            ("Lumi", "Polish breathing orb"),
            ("Lumi", "Design analytics grid"),
            ("QA Project", "QA task search project"),
            ("QA Project", "Regression checklist"),
            ("QA Project", "Mobile layout pass"),
            ("Manual QA", "Manual log regression"),
            ("Manual QA", "Reflection form QA"),
            ("Ops Review", "Prepare analytics review"),
            ("Ops Review", "Weekly status notes"),
            ("Ops Review", "Triage follow-ups"),
            ("AI Coach", "Draft reflection prompts"),
            ("AI Coach", "LLM insight prompt"),
            ("AI Coach", "Summarize focus patterns"),
            ("Calendar", "Calendar focus blocks"),
            ("Calendar", "Morning planning flow"),
            ("Calendar", "Yandex sync review"),
            ("Inbox Zero", "Inbox capture cleanup"),
            ("Inbox Zero", "Email triage design"),
            ("Inbox Zero", "Notification copy pass"),
            ("Release", "Launch notes draft"),
            ("Release", "PR checklist update"),
            ("Release", "Screenshots for PR"),
            (None, None),
        ]
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
        await session.execute(
            delete(FocusSession).where(
                FocusSession.user_id == user.id,
                FocusSession.status == FocusSessionStatus.COMPLETED,
                FocusSession.intention.in_(intentions),
                FocusSession.accomplished_text.in_(results),
                FocusSession.next_step_text.in_(next_steps),
            )
        )
        durations = [18, 22, 25, 32, 39, 45, 50, 55, 65, 75, 90]
        hours = [6, 7, 9, 10, 11, 13, 15, 17, 19, 21, 23]
        focus_seed = []
        for index in range(100):
            day_offset = -(index % 30)
            project, task_title = project_tasks[index % len(project_tasks)]
            hour = hours[(index * 7) % len(hours)]
            minute = (index * 11) % 50
            focus_seed.append(
                (
                    day_offset,
                    hour,
                    minute,
                    intentions[index % len(intentions)],
                    project,
                    task_title,
                    durations[(index * 5) % len(durations)],
                    3 + (index % 3),
                    results[index % len(results)],
                    next_steps[index % len(next_steps)],
                )
            )
        session_created = 0
        for offset, hour, minute, intention, project, task_title, minutes, score, done, next_step in focus_seed:
            started = (today + timedelta(days=offset)).replace(hour=hour, minute=minute)
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
        created.append(f"focus sessions seeded={session_created}")

    print("Seed готов. Создано/проверено:")
    for line in created:
        print(f"  • {line}")
    await dispose_engine()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
