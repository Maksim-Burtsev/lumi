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


async def test_snoozed_tasks_hidden_from_active_lists_but_searchable(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        snoozed = await service.create_task(u, title="Отложенная задача")
        visible = await service.create_task(u, title="Видимая задача")
        snoozed = await service.snooze_task(u, snoozed, preset="tomorrow")

        assert snoozed.snoozed_until is not None
        assert snoozed.reminder_at == snoozed.snoozed_until
        assert [t.id for t in await service.list_active(u)] == [visible.id]
        assert [t.id for t in await service.list_tasks(u, filter_="all")] == [visible.id]
        summary = await service.count_summary(u)
        assert summary["tasks_active"] == 1

        candidates = await service.find_open_rename_candidates(u, "отложенная задача")
        assert [task.id for task in candidates] == [snoozed.id]


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


async def test_rename_active_task_by_title_returns_not_found_for_done_task(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        task = await service.create_task(u, title="Закрытая задача")
        await service.complete_task(u, task)

        result = await service.rename_active_task_by_title(
            u,
            current_title="Закрытая задача",
            new_title="Новое название",
            actor="agent",
        )

        assert result.status == "not_found"
        assert result.task is None
        assert task.title == "Закрытая задача"


async def test_rename_active_task_by_title_updates_exact_match_and_audits(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        task = await service.create_task(u, title="Написать короткий сценарий теста accept/reject")
        task_id = task.id

        result = await service.rename_active_task_by_title(
            u,
            current_title="Написать короткий сценарий теста accept/reject",
            new_title="Свой аналог session в Lumi интегрировать",
            actor="agent",
        )

        assert result.status == "renamed"
        assert result.task is not None
        assert result.task.id == task_id
        assert result.old_title == "Написать короткий сценарий теста accept/reject"
        assert result.new_title == "Свой аналог session в Lumi интегрировать"

    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task = await TaskService(session).get(u, task_id)
        assert task.title == "Свой аналог session в Lumi интегрировать"

        events = await session.execute(
            select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at)
        )
        created, updated = list(events.scalars())
        assert created.event_type == "created"
        assert updated.event_type == "updated"
        assert updated.actor == "agent"
        assert updated.before_json["title"] == "Написать короткий сценарий теста accept/reject"
        assert updated.after_json["title"] == "Свой аналог session в Lumi интегрировать"


async def test_rename_active_task_by_title_returns_ambiguous_for_duplicate_matches(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        first = await service.create_task(u, title="Одинаковая задача")
        second = await service.create_task(u, title="  одинаковая   задача  ")

        result = await service.rename_active_task_by_title(
            u,
            current_title="одинаковая задача",
            new_title="Новое название",
            actor="agent",
        )

        assert result.status == "ambiguous"
        assert result.task is None
        assert {first.title, second.title} == {"Одинаковая задача", "одинаковая   задача"}


async def test_rename_active_task_by_title_updates_single_fuzzy_match(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        task = await service.create_task(u, title="Свой аналог session в Lumi интегрировать")
        task_id = task.id
        await service.create_task(u, title="Сделать real-time обновления в mini-app Lumi")

        result = await service.rename_active_task_by_title(
            u,
            current_title="аналог сешн в lumi",
            new_title="Интегрировать свой session в Lumi",
            actor="agent",
        )

        assert result.status == "renamed"
        assert result.task is not None
        assert result.task.id == task_id
        assert result.old_title == "Свой аналог session в Lumi интегрировать"


async def test_rename_active_task_by_title_uses_project_and_tags_to_pick_match(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        await service.create_task(
            u,
            title="Написать короткий сценарий теста accept/reject",
            project="Работа",
            tags=["qa"],
        )
        expected = await service.create_task(
            u,
            title="Написать короткий сценарий теста accept/reject",
            project="Lumi",
            tags=["test"],
        )

        result = await service.rename_active_task_by_title(
            u,
            current_title="короткий сценарий теста",
            new_title="Сценарий accept reject готов",
            project="Lumi",
            tags=["test"],
            actor="agent",
        )

        assert result.status == "renamed"
        assert result.task is not None
        assert result.task.id == expected.id


async def test_rename_active_task_by_title_returns_ambiguous_for_multiple_fuzzy_matches(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        first = await service.create_task(u, title="Написать сценарий теста accept reject")
        second = await service.create_task(u, title="Написать сценарий теста approve reject")

        result = await service.rename_active_task_by_title(
            u,
            current_title="написать сценарий теста",
            new_title="Новый сценарий",
            actor="agent",
        )

    assert result.status == "ambiguous"
    assert result.task is None
    assert {candidate.id for candidate in result.candidates} == {first.id, second.id}


async def test_exact_substring_candidate_wins_over_similar_marker_tasks(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        await service.create_task(u, title="посмотреть ответ chatGPT по QA-TIME-FWD-2342")
        exact = await service.create_task(u, title="посмотреть ответ chatGPT по QA-TIME-FWD-0011")

        candidates = await service.find_open_rename_candidates(u, "QA-TIME-FWD-0011")

    assert [task.id for task in candidates] == [exact.id]


async def test_rename_open_task_by_id_renames_only_selected_candidate(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        first = await service.create_task(u, title="Написать сценарий теста accept reject")
        second = await service.create_task(u, title="Написать сценарий теста approve reject")

        result = await service.rename_open_task_by_id(
            u,
            second.id,
            new_title="Новый сценарий",
            actor="user",
        )

        assert result.status == "renamed"
        assert result.task is not None
        assert result.task.id == second.id
        assert first.title == "Написать сценарий теста accept reject"
        assert second.title == "Новый сценарий"


async def test_bulk_update_candidates_and_tag_operations(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = TaskService(session)
        first = await service.create_task(
            u,
            title="Решить вопрос с мониторингом в Lumi",
            project="Работа",
            tags=["lumi", "old"],
        )
        second = await service.create_task(
            u,
            title="Поддержать несколько фото к сообщению",
            project="Работа",
            tags=["lumi", "feature"],
        )
        unrelated = await service.create_task(
            u,
            title="Купить капсулы для стирки",
            project="Работа",
            tags=["покупки"],
        )
        done = await service.create_task(
            u,
            title="Lumi закрытая задача",
            project="Работа",
            tags=["lumi"],
        )
        await service.complete_task(u, done)

        candidates = await service.find_bulk_update_candidates(
            u,
            task_query="Lumi",
            from_project="Работа",
            status="open",
        )
        assert {task.id for task in candidates} == {first.id, second.id}

        updated = await service.bulk_update_tasks(
            u,
            candidates,
            {"project": None},
            tags_add=["feature", "qa"],
            tags_remove=["old"],
            actor="agent",
        )

        assert {task.id for task in updated} == {first.id, second.id}
        assert first.project is None
        assert second.project is None
        assert first.tags == ["lumi", "feature", "qa"]
        assert second.tags == ["lumi", "feature", "qa"]
        assert unrelated.project == "Работа"
        assert unrelated.tags == ["покупки"]
        assert done.project == "Работа"
