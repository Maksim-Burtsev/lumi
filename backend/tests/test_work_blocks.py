from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from lumi.api.serializers import event_to_dict
from lumi.db.models import CalendarEvent, CalendarEventStatus, CalendarSource, TaskStatus, User
from lumi.db.session import session_scope
from lumi.services.calendar import CalendarService
from lumi.services.focus import FocusService
from lumi.services.planning import PlanningService, _local_candidate_roundtrips
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


def test_planning_rejects_nonexistent_and_ambiguous_dst_local_times():
    assert not _local_candidate_roundtrips(
        datetime(2035, 3, 25, 2, 30),
        "Europe/Berlin",
    )
    assert not _local_candidate_roundtrips(
        datetime(2035, 10, 28, 2, 30),
        "Europe/Berlin",
    )
    assert _local_candidate_roundtrips(
        datetime(2035, 3, 25, 10, 0),
        "Europe/Berlin",
    )


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


async def test_external_move_marks_work_block_and_creates_one_explicit_alternative(
    db_session,
):
    user = await _work_user(db_session)
    task = await TaskService(db_session).create_task(user, title="Protected work")
    calendar = CalendarService(db_session)
    start_at = datetime(2035, 7, 11, 10, tzinfo=UTC)
    created = await WorkBlockService(db_session).create(
        user,
        task_id=task.id,
        title="Protected work",
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
        status=CalendarEventStatus.CONFIRMED,
    )
    assert created.event is not None
    external = await calendar.upsert_external_event(
        user,
        source=CalendarSource.GOOGLE,
        external_calendar_id="primary",
        external_event_id="moving-meeting",
        title="Moving meeting",
        start_at=start_at + timedelta(hours=3),
        end_at=start_at + timedelta(hours=4),
    )

    moved = await calendar.upsert_external_event(
        user,
        source=CalendarSource.GOOGLE,
        external_calendar_id="primary",
        external_event_id="moving-meeting",
        title="Moving meeting",
        start_at=start_at + timedelta(minutes=15),
        end_at=start_at + timedelta(minutes=45),
    )

    payload = event_to_dict(created.event)
    assert created.event.start_at == start_at
    assert moved.id == external.id
    assert moved.start_at == start_at + timedelta(minutes=15)
    assert payload["work_block_conflict"]["status"] == "impacted"
    assert payload["work_block_conflict"]["external_event_id"] == str(external.id)
    with pytest.raises(ValueError, match="planned_event_conflicted"):
        await FocusService(db_session).start_session(
            user,
            planned_event_id=created.event.id,
            intention="Must use the alternative",
            planned_minutes=60,
        )
    alternative_id = uuid.UUID(payload["work_block_conflict"]["alternative_event_id"])
    alternative = await db_session.get(CalendarEvent, alternative_id)
    assert alternative is not None
    assert alternative.status == CalendarEventStatus.PROPOSED
    assert alternative.start_at != created.event.start_at
    assert event_to_dict(alternative)["alternative_for_event_id"] == str(created.event.id)

    await calendar.upsert_external_event(
        user,
        source=CalendarSource.GOOGLE,
        external_calendar_id="primary",
        external_event_id="moving-meeting",
        title="Moving meeting",
        start_at=start_at + timedelta(minutes=15),
        end_at=start_at + timedelta(minutes=45),
    )
    alternatives = list(
        (
            await db_session.execute(
                select(CalendarEvent).where(
                    CalendarEvent.user_id == user.id,
                    CalendarEvent.metadata_["alternative_for_event_id"].astext
                    == str(created.event.id),
                )
            )
        ).scalars()
    )
    assert [item.id for item in alternatives] == [alternative_id]

    cancelled = await calendar.reconcile_external_events(
        user,
        source=CalendarSource.GOOGLE,
        external_calendar_id="primary",
        start_at=start_at.replace(hour=0),
        end_at=start_at.replace(hour=23),
        seen_event_ids=set(),
    )
    assert cancelled == 1
    await db_session.refresh(created.event)
    assert created.event.start_at == start_at
    assert event_to_dict(created.event)["work_block_conflict"] is None
    assert (created.event.metadata_["work_block_conflict"])["status"] == "resolved"
    assert alternative.status == CalendarEventStatus.CANCELLED


async def test_external_meeting_invalidates_planning_proposal_and_offers_alternative(
    db_session,
):
    user = await _work_user(db_session)
    task = await TaskService(db_session).create_task(user, title="Planning proposal")
    start_at = datetime(2035, 7, 11, 10, tzinfo=UTC)
    original = await WorkBlockService(db_session).create(
        user,
        task_id=task.id,
        title="Planning proposal",
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
        metadata={
            "plan_batch_id": "batch-1",
            "planning_request_id": "request-1",
            "proposal_expires_at": "2035-07-11T12:00:00+00:00",
        },
    )
    assert original.event is not None

    external = await CalendarService(db_session).upsert_external_event(
        user,
        source=CalendarSource.GOOGLE,
        external_calendar_id="primary",
        external_event_id="proposal-conflict",
        title="New external meeting",
        start_at=start_at + timedelta(minutes=15),
        end_at=start_at + timedelta(minutes=45),
    )

    conflict = original.event.metadata_["work_block_conflict"]
    alternative = await db_session.get(
        CalendarEvent,
        uuid.UUID(conflict["alternative_event_id"]),
    )
    assert original.event.status == CalendarEventStatus.CANCELLED
    assert alternative is not None
    assert alternative.status == CalendarEventStatus.PROPOSED
    assert alternative.start_at != original.event.start_at
    assert alternative.metadata_["planning_request_id"] == "request-1"
    assert external.status == CalendarEventStatus.CONFIRMED
    assert external.start_at == start_at + timedelta(minutes=15)


async def test_accepting_conflict_alternative_cancels_only_original_work_block(
    user,
    db_session,
):
    task = await TaskService(db_session).create_task(user, title="Explicit replacement")
    calendar = CalendarService(db_session)
    start_at = datetime(2035, 7, 11, 10, tzinfo=UTC)
    original = await WorkBlockService(db_session).create(
        user,
        task_id=task.id,
        title="Explicit replacement",
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
        status=CalendarEventStatus.CONFIRMED,
    )
    assert original.event is not None
    external = await calendar.upsert_external_event(
        user,
        source=CalendarSource.GOOGLE,
        external_calendar_id="primary",
        external_event_id="accepted-alternative-meeting",
        title="Fixed meeting",
        start_at=start_at + timedelta(minutes=15),
        end_at=start_at + timedelta(minutes=45),
    )
    conflict = event_to_dict(original.event)["work_block_conflict"]
    assert conflict is not None
    alternative_id = uuid.UUID(conflict["alternative_event_id"])

    confirmed = await WorkBlockService(db_session).confirm(
        user,
        event_id=alternative_id,
    )

    assert confirmed.status == WorkBlockResultStatus.CONFIRMED
    assert confirmed.event is not None
    assert confirmed.event.status == CalendarEventStatus.CONFIRMED
    assert original.event.status == CalendarEventStatus.CANCELLED
    assert original.event.metadata_["work_block_conflict"]["status"] == "replaced"
    assert external.status == CalendarEventStatus.CONFIRMED
    assert external.start_at == start_at + timedelta(minutes=15)
    assert external.end_at == start_at + timedelta(minutes=45)


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
        self.calls = 0

    async def complete_json(self, **_kwargs):
        self.calls += 1
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


async def test_planning_applies_work_block_buffer_before_any_write(db_session):
    user = await _work_user(db_session)
    first = await TaskService(db_session).create_task(user, title="First task")
    second = await TaskService(db_session).create_task(user, title="Second task")
    gateway = _PlanningGateway(
        {
            "summary": "Buffered plan",
            "blocks": [
                {
                    "title": "First block",
                    "task_id": str(first.id),
                    "start_at_local": "2035-07-11T10:00:00",
                    "end_at_local": "2035-07-11T11:00:00",
                },
                {
                    "title": "Too close",
                    "task_id": str(second.id),
                    "start_at_local": "2035-07-11T11:05:00",
                    "end_at_local": "2035-07-11T12:00:00",
                },
            ],
        }
    )

    _, created = await PlanningService(db_session, llm=gateway).propose_day_plan(
        user,
        day=datetime(2035, 7, 11, 9, tzinfo=UTC),
    )

    assert [event.title for event in created] == ["First block"]


async def test_planning_request_is_idempotent_and_rejects_deadline_violation(db_session):
    user = await _work_user(db_session)
    task = await TaskService(db_session).create_task(
        user,
        title="Deadline-bound task",
        due_at=datetime(2035, 7, 11, 10, 30, tzinfo=UTC),
    )
    gateway = _PlanningGateway(
        {
            "summary": "Ranked plan",
            "blocks": [
                {
                    "title": "Past deadline",
                    "task_id": str(task.id),
                    "start_at_local": "2035-07-11T10:00:00",
                    "end_at_local": "2035-07-11T11:00:00",
                }
            ],
        }
    )
    planning = PlanningService(db_session, llm=gateway)

    summary, created = await planning.propose_day_plan(
        user,
        day=datetime(2035, 7, 11, 9, tzinfo=UTC),
        request_id="deadline-request",
    )

    assert summary.startswith("No safe blocks")
    assert created == []

    task.due_at = datetime(2035, 7, 11, 11, 30, tzinfo=UTC)
    repeated_empty_summary, repeated_empty = await planning.propose_day_plan(
        user,
        day=datetime(2035, 7, 11, 9, tzinfo=UTC),
        request_id="deadline-request",
    )

    assert repeated_empty_summary == summary
    assert repeated_empty == []
    assert gateway.calls == 1

    summary, created = await planning.propose_day_plan(
        user,
        day=datetime(2035, 7, 11, 9, tzinfo=UTC),
        request_id="stable-request",
    )
    repeated_summary, repeated = await planning.propose_day_plan(
        user,
        day=datetime(2035, 7, 11, 9, tzinfo=UTC),
        request_id="stable-request",
    )

    assert summary.startswith("Ranked plan")
    assert len(created) == 1
    assert repeated_summary.startswith("Plan already queued")
    assert [event.id for event in repeated] == [created[0].id]
    assert created[0].metadata_["planning_request_id"] == "stable-request"
    assert created[0].metadata_["proposal_expires_at"]
    assert gateway.calls == 2

    created[0].metadata_ = {
        **created[0].metadata_,
        "proposal_expires_at": "2000-01-01T00:00:00+00:00",
    }
    expired_summary, expired = await planning.propose_day_plan(
        user,
        day=datetime(2035, 7, 11, 9, tzinfo=UTC),
        request_id="stable-request",
    )

    assert expired_summary == "This planning request was already processed."
    assert expired == []
    assert gateway.calls == 2


async def test_failed_replan_keeps_existing_future_proposals(db_session, monkeypatch):
    now = datetime(2035, 7, 11, 12, tzinfo=UTC)
    monkeypatch.setattr("lumi.services.planning.utc_now", lambda: now)
    user = await _work_user(db_session)
    existing_task = await TaskService(db_session).create_task(user, title="Existing")
    await TaskService(db_session).create_task(user, title="Still active")
    existing = await WorkBlockService(db_session).create(
        user,
        task_id=existing_task.id,
        title="Existing proposal",
        start_at=now.replace(hour=15),
        end_at=now.replace(hour=16),
    )
    assert existing.event is not None

    class _FailingGateway:
        async def complete_json(self, **_kwargs):
            raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await PlanningService(db_session, llm=_FailingGateway()).propose_day_plan(
            user,
            mode="replan",
            request_id="failed-replan",
        )

    assert existing.event.status == CalendarEventStatus.PROPOSED


async def test_replan_cancels_only_future_proposals(db_session):
    user = await _work_user(db_session)
    tasks = TaskService(db_session)
    morning_task = await tasks.create_task(user, title="Morning")
    afternoon_task = await tasks.create_task(user, title="Afternoon")
    manual_task = await tasks.create_task(user, title="Manual")
    alternative_task = await tasks.create_task(user, title="Alternative")
    service = WorkBlockService(db_session)
    day = datetime(2035, 7, 11, tzinfo=UTC)
    morning = await service.create(
        user,
        task_id=morning_task.id,
        title="Morning",
        start_at=day.replace(hour=9),
        end_at=day.replace(hour=10),
    )
    afternoon = await service.create(
        user,
        task_id=afternoon_task.id,
        title="Afternoon",
        start_at=day.replace(hour=15),
        end_at=day.replace(hour=16),
        metadata={"plan_batch_id": "replaced-plan"},
    )
    manual = await service.create(
        user,
        task_id=manual_task.id,
        title="Manual",
        start_at=day.replace(hour=16, minute=30),
        end_at=day.replace(hour=17),
    )
    alternative = await service.create(
        user,
        task_id=alternative_task.id,
        title="Alternative",
        start_at=day.replace(hour=17, minute=30),
        end_at=day.replace(hour=18),
        metadata={
            "plan_batch_id": "replaced-plan",
            "alternative_for_event_id": str(uuid.uuid4()),
        },
    )
    assert morning.event is not None
    assert afternoon.event is not None
    assert manual.event is not None
    assert alternative.event is not None

    cancelled = await CalendarService(db_session).cancel_proposed_blocks(
        user,
        day=day,
        future_only=True,
        planning_only=True,
        now=day.replace(hour=12),
    )

    assert cancelled == 1
    assert morning.event.status == CalendarEventStatus.PROPOSED
    assert afternoon.event.status == CalendarEventStatus.CANCELLED
    assert manual.event.status == CalendarEventStatus.PROPOSED
    assert alternative.event.status == CalendarEventStatus.PROPOSED


async def test_planning_proposal_revalidates_expiry_and_deadline_on_confirm(db_session):
    user = await _work_user(db_session)
    tasks = TaskService(db_session)
    expired_task = await tasks.create_task(user, title="Expired")
    deadline_task = await tasks.create_task(
        user,
        title="Deadline changed",
        due_at=datetime(2035, 7, 11, 12, 30, tzinfo=UTC),
    )
    service = WorkBlockService(db_session)
    day = datetime(2035, 7, 11, tzinfo=UTC)
    expired = await service.create(
        user,
        task_id=expired_task.id,
        title="Expired",
        start_at=day.replace(hour=9),
        end_at=day.replace(hour=10),
        metadata={
            "plan_batch_id": "expired",
            "proposal_expires_at": "2000-01-01T00:00:00+00:00",
        },
    )
    deadline = await service.create(
        user,
        task_id=deadline_task.id,
        title="Deadline changed",
        start_at=day.replace(hour=11),
        end_at=day.replace(hour=12),
        metadata={"plan_batch_id": "deadline"},
    )
    assert expired.event is not None
    assert deadline.event is not None

    deadline_task.due_at = datetime(2035, 7, 11, 10, 30, tzinfo=UTC)
    expired_result = await service.confirm(user, event_id=expired.event.id)
    deadline_result = await service.confirm(user, event_id=deadline.event.id)

    assert (expired_result.status, expired_result.reason) == (
        WorkBlockResultStatus.STALE,
        WorkBlockReason.PROPOSAL_EXPIRED,
    )
    assert (deadline_result.status, deadline_result.reason) == (
        WorkBlockResultStatus.STALE,
        WorkBlockReason.PROPOSAL_CHANGED,
    )
    assert expired.event.status == CalendarEventStatus.CANCELLED
    assert deadline.event.status == CalendarEventStatus.CANCELLED
