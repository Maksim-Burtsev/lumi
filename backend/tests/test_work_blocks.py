from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from lumi.db.models import CalendarEventStatus, CalendarSource, TaskStatus, User
from lumi.db.session import session_scope
from lumi.services.calendar import CalendarService
from lumi.services.planning import PlanningService
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.services.work_blocks import (
    WorkBlockReason,
    WorkBlockResultStatus,
    WorkBlockService,
)

from .conftest import TEST_TELEGRAM_ID


def _work_settings() -> dict:
    return {
        "planning": {
            "work_days": [0, 1, 2, 3, 4, 5, 6],
            "work_hours": {"start": "09:00", "end": "19:00"},
        }
    }


async def _work_user(db_session, telegram_id: int = TEST_TELEGRAM_ID):
    user = await UserService(db_session).ensure_user(telegram_id)
    user.timezone = "UTC"
    user.settings = _work_settings()
    return user


async def test_work_block_validates_ownership_hours_buffer_stale_and_idempotency(db_session):
    user = await _work_user(db_session)
    other_user = await _work_user(db_session, TEST_TELEGRAM_ID + 1)
    tasks = TaskService(db_session)
    first_task = await tasks.create_task(user, title="First")
    second_task = await tasks.create_task(user, title="Second")
    closed_task = await tasks.create_task(user, title="Closed")
    foreign_task = await tasks.create_task(other_user, title="Foreign")
    await tasks.complete_task(user, closed_task)
    service = WorkBlockService(db_session)
    day = datetime(2035, 7, 11, tzinfo=UTC)

    foreign = await service.create(
        user,
        task_id=foreign_task.id,
        title="Foreign",
        start_at=day.replace(hour=9),
        end_at=day.replace(hour=10),
    )
    assert (foreign.status, foreign.reason) == (
        WorkBlockResultStatus.NOT_FOUND,
        WorkBlockReason.TASK_NOT_FOUND,
    )

    closed = await service.create(
        user,
        task_id=closed_task.id,
        title="Closed",
        start_at=day.replace(hour=9),
        end_at=day.replace(hour=10),
    )
    assert (closed.status, closed.reason) == (
        WorkBlockResultStatus.INVALID,
        WorkBlockReason.TASK_CLOSED,
    )

    outside = await service.create(
        user,
        task_id=first_task.id,
        title="Too early",
        start_at=day.replace(hour=8),
        end_at=day.replace(hour=9),
    )
    assert (outside.status, outside.reason) == (
        WorkBlockResultStatus.INVALID,
        WorkBlockReason.OUTSIDE_WORK_HOURS,
    )

    first = await service.create(
        user,
        task_id=first_task.id,
        title="Reserved",
        start_at=day.replace(hour=10),
        end_at=day.replace(hour=11),
        status=CalendarEventStatus.CONFIRMED,
    )
    assert first.status == WorkBlockResultStatus.CONFIRMED

    buffered_conflict = await service.create(
        user,
        task_id=second_task.id,
        title="Nine minute gap",
        start_at=day.replace(hour=11, minute=9),
        end_at=day.replace(hour=12),
    )
    assert buffered_conflict.status == WorkBlockResultStatus.CONFLICT
    assert buffered_conflict.reason == WorkBlockReason.CALENDAR_CONFLICT
    assert buffered_conflict.conflict is first.event

    exact_boundary = await service.create(
        user,
        task_id=second_task.id,
        title=None,
        start_at=day.replace(hour=11, minute=10),
        end_at=day.replace(hour=12, minute=10),
    )
    assert exact_boundary.status == WorkBlockResultStatus.PROPOSED
    assert exact_boundary.event is not None
    assert exact_boundary.event.title == second_task.title

    stale = await service.confirm(
        user,
        event_id=exact_boundary.event.id,
        expected_updated_at=exact_boundary.event.updated_at - timedelta(seconds=1),
    )
    assert (stale.status, stale.reason) == (
        WorkBlockResultStatus.STALE,
        WorkBlockReason.PROPOSAL_CHANGED,
    )

    confirmed = await service.confirm(user, event_id=exact_boundary.event.id)
    assert confirmed.status == WorkBlockResultStatus.CONFIRMED
    repeated = await service.confirm(user, event_id=exact_boundary.event.id)
    assert repeated.status == WorkBlockResultStatus.ALREADY_CONFIRMED


async def test_work_block_confirmation_rechecks_external_conflict(db_session):
    user = await _work_user(db_session)
    task = await TaskService(db_session).create_task(user, title="Proposal")
    start_at = datetime(2035, 7, 11, 14, tzinfo=UTC)
    result = await WorkBlockService(db_session).create(
        user,
        task_id=task.id,
        title="Proposal",
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
    )
    assert result.event is not None

    external = await CalendarService(db_session).upsert_external_event(
        user,
        source=CalendarSource.GOOGLE,
        external_calendar_id="primary",
        external_event_id="new-conflict",
        title="New fixed meeting",
        start_at=start_at + timedelta(minutes=30),
        end_at=start_at + timedelta(hours=1, minutes=30),
    )
    confirmed = await WorkBlockService(db_session).confirm(user, event_id=result.event.id)

    assert confirmed.status == WorkBlockResultStatus.CONFLICT
    assert confirmed.conflict is external
    assert result.event.status == CalendarEventStatus.PROPOSED
    assert external.start_at == start_at + timedelta(minutes=30)


async def test_concurrent_work_block_confirmation_is_idempotent():
    async with session_scope() as session:
        user = await _work_user(session)
        task = await TaskService(session).create_task(user, title="Race-safe block")
        result = await WorkBlockService(session).create(
            user,
            task_id=task.id,
            title="Race-safe block",
            start_at=datetime(2035, 7, 11, 16, tzinfo=UTC),
            end_at=datetime(2035, 7, 11, 17, tzinfo=UTC),
        )
        assert result.event is not None
        user_id = user.id
        event_id = result.event.id

    async def confirm() -> WorkBlockResultStatus:
        async with session_scope() as session:
            user = await session.get(User, user_id)
            assert user is not None
            result = await WorkBlockService(session).confirm(user, event_id=event_id)
            return result.status

    statuses = await asyncio.gather(confirm(), confirm())

    assert sorted(statuses) == sorted(
        [WorkBlockResultStatus.CONFIRMED, WorkBlockResultStatus.ALREADY_CONFIRMED]
    )


class _PlanningGateway:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    async def complete_json(self, **_kwargs):
        return self.payload


async def test_planning_only_creates_valid_owned_non_overlapping_work_blocks(db_session):
    user = await _work_user(db_session)
    first = await TaskService(db_session).create_task(user, title="Owned task")
    second = await TaskService(db_session).create_task(user, title="Second owned task")
    unknown_id = uuid.uuid4()
    day = datetime(2035, 7, 11, 9, tzinfo=UTC)
    gateway = _PlanningGateway(
        {
            "summary": "Safe plan",
            "blocks": [
                {
                    "title": "Valid block",
                    "task_id": str(first.id),
                    "start_at_local": "2035-07-11T10:00:00",
                    "end_at_local": "2035-07-11T11:00:00",
                },
                {
                    "title": "Unknown task",
                    "task_id": str(unknown_id),
                    "start_at_local": "2035-07-11T12:00:00",
                    "end_at_local": "2035-07-11T13:00:00",
                },
                {
                    "title": "Overlapping block",
                    "task_id": str(second.id),
                    "start_at_local": "2035-07-11T10:30:00",
                    "end_at_local": "2035-07-11T11:30:00",
                },
            ],
        }
    )

    summary, created = await PlanningService(db_session, llm=gateway).propose_day_plan(
        user,
        day=day,
    )

    assert summary.startswith("Safe plan")
    assert [event.title for event in created] == ["Valid block"]
    assert created[0].source_task_id == first.id
    assert created[0].status == CalendarEventStatus.PROPOSED
    assert second.status in {TaskStatus.INBOX, TaskStatus.ACTIVE}
