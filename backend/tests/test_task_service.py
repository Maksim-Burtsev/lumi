from datetime import timedelta

from sqlalchemy import select

from lumi.db.models import TaskEvent, TaskStatus
from lumi.db.session import session_scope
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.utils.time import utc_now

from .conftest import TEST_TELEGRAM_ID


async def test_create_complete_snooze(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        task = await service.create_task(
            u, title="Написать Саше", priority="high",
            due_at=utc_now() + timedelta(days=1),
            reminder_at=utc_now() + timedelta(days=1),
        )
        assert task.status == TaskStatus.ACTIVE
        task_id = task.id

    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        task = await service.get(u, task_id)
        task = await service.snooze_task(u, task, preset="tomorrow")
        assert task.snoozed_until is not None
        assert task.reminder_at == task.snoozed_until

        task = await service.complete_task(u, task)
        assert task.status == TaskStatus.DONE
        assert task.completed_at is not None

    async with session_scope() as session:
        events = await session.execute(
            select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at)
        )
        types = [e.event_type for e in events.scalars()]
        assert types == ["created", "snoozed", "completed"]


async def test_due_reminders_query_and_mark_sent(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        due = await service.create_task(u, title="Просрочено", reminder_at=utc_now() - timedelta(minutes=5))
        await service.create_task(u, title="Будущее", reminder_at=utc_now() + timedelta(hours=2))
        await service.create_task(u, title="Без напоминания")
        due_id = due.id

    async with session_scope() as session:
        service = TaskService(session)
        found = await service.find_due_reminders()
        assert [t.id for t in found] == [due_id]
        await service.mark_reminder_sent(found[0])

    async with session_scope() as session:
        service = TaskService(session)
        assert await service.find_due_reminders() == []


async def test_list_filters(user):
    from lumi.utils.time import local_day_bounds

    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        # Keep the due time inside the user's local "today" even late at night.
        _, day_end = local_day_bounds(utc_now(), u.timezone)
        due_today = min(utc_now() + timedelta(hours=2), day_end - timedelta(minutes=1))
        await service.create_task(u, title="Сегодня", due_at=due_today)
        await service.create_task(u, title="Через неделю", due_at=utc_now() + timedelta(days=7))
        done = await service.create_task(u, title="Готово")
        await service.complete_task(u, done)

        today = await service.list_tasks(u, filter_="today")
        assert [t.title for t in today] == ["Сегодня"]
        upcoming = await service.list_tasks(u, filter_="upcoming")
        assert "Через неделю" in [t.title for t in upcoming]
        done_list = await service.list_tasks(u, filter_="done")
        assert [t.title for t in done_list] == ["Готово"]
