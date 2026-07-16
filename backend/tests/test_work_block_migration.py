from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from lumi.db.models import CalendarEvent, FocusSession, Task


def _named(items, name: str):
    return next(item for item in items if item.name == name)


def test_work_block_ownership_chain_is_enforced_by_metadata():
    task_identity = _named(Task.__table__.constraints, "uq_tasks_user_id_id")
    assert isinstance(task_identity, UniqueConstraint)
    assert tuple(task_identity.columns.keys()) == ("user_id", "id")

    calendar_task = _named(
        CalendarEvent.__table__.constraints,
        "fk_calendar_events_user_source_task",
    )
    assert isinstance(calendar_task, ForeignKeyConstraint)
    assert tuple(calendar_task.columns.keys()) == ("user_id", "source_task_id")
    assert tuple(element.target_fullname for element in calendar_task.elements) == (
        "tasks.user_id",
        "tasks.id",
    )
    assert calendar_task.ondelete == "RESTRICT"

    calendar_identity = _named(
        CalendarEvent.__table__.constraints,
        "uq_calendar_events_user_id_source_task",
    )
    assert isinstance(calendar_identity, UniqueConstraint)
    assert tuple(calendar_identity.columns.keys()) == ("user_id", "id", "source_task_id")

    internal_only = _named(
        CalendarEvent.__table__.constraints,
        "calendar_event_source_task_internal",
    )
    assert isinstance(internal_only, CheckConstraint)
    assert str(internal_only.sqltext) == "source_task_id IS NULL OR source = 'internal'"

    focus_task = _named(FocusSession.__table__.constraints, "fk_focus_sessions_user_task")
    assert isinstance(focus_task, ForeignKeyConstraint)
    assert tuple(focus_task.columns.keys()) == ("user_id", "task_id")
    assert focus_task.ondelete == "RESTRICT"

    planned_block = _named(
        FocusSession.__table__.constraints,
        "fk_focus_sessions_planned_work_block",
    )
    assert isinstance(planned_block, ForeignKeyConstraint)
    assert tuple(planned_block.columns.keys()) == ("user_id", "planned_event_id", "task_id")
    assert tuple(element.target_fullname for element in planned_block.elements) == (
        "calendar_events.user_id",
        "calendar_events.id",
        "calendar_events.source_task_id",
    )
    assert planned_block.ondelete == "RESTRICT"

    planned_requires_task = _named(
        FocusSession.__table__.constraints,
        "focus_session_planned_event_requires_task",
    )
    assert isinstance(planned_requires_task, CheckConstraint)
    assert str(planned_requires_task.sqltext) == "planned_event_id IS NULL OR task_id IS NOT NULL"

    assert {
        "ix_calendar_events_user_source_task",
    } <= {index.name for index in CalendarEvent.__table__.indexes}
    assert {
        "ix_focus_sessions_user_task",
        "ix_focus_sessions_user_planned_event",
    } <= {index.name for index in FocusSession.__table__.indexes}
