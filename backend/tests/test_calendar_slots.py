from datetime import UTC, datetime, timedelta

from lumi.db.models import CalendarEventStatus, CalendarSource
from lumi.services.calendar import CalendarService, merge_busy_intervals, subtract_intervals
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.utils.time import get_zone

from .conftest import TEST_TELEGRAM_ID


def _t(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 10, hour, minute, tzinfo=UTC)


def test_merge_overlapping():
    merged = merge_busy_intervals([(_t(10), _t(11)), (_t(10, 30), _t(12)), (_t(14), _t(15))])
    assert merged == [(_t(10), _t(12)), (_t(14), _t(15))]


def test_merge_touching():
    merged = merge_busy_intervals([(_t(10), _t(11)), (_t(11), _t(12))])
    assert merged == [(_t(10), _t(12))]


def test_merge_empty():
    assert merge_busy_intervals([]) == []


def test_free_slots_basic():
    window = (_t(9), _t(19))
    busy = [(_t(10), _t(11)), (_t(13), _t(14))]
    free = subtract_intervals(window, busy, min_duration=timedelta(minutes=60))
    # 9:00–9:50 (buffer), 11:10–12:50, 14:10–19:00
    assert len(free) == 2  # first gap is only 50 min after buffer
    assert free[0][0] == _t(11, 10)
    assert free[1] == (_t(14, 10), _t(19))


def test_free_slots_empty_calendar():
    window = (_t(9), _t(19))
    free = subtract_intervals(window, [], min_duration=timedelta(minutes=30))
    assert free == [(_t(9), _t(19))]


def test_free_slots_fully_busy():
    window = (_t(9), _t(12))
    free = subtract_intervals(window, [(_t(8), _t(13))], min_duration=timedelta(minutes=30))
    assert free == []


async def test_find_free_slots_uses_planning_work_window_and_local_workday(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    user.timezone = "Pacific/Chatham"
    user.settings = {
        "planning": {
            "work_days": [2],
            "work_hours": {"start": "09:15", "end": "10:45"},
        }
    }
    service = CalendarService(db_session)

    slots = await service.find_free_slots(
        user,
        day=datetime(2027, 7, 14, 12),
        duration_minutes=30,
    )

    assert len(slots) == 1
    zone = get_zone(user.timezone)
    assert slots[0][0].astimezone(zone).strftime("%Y-%m-%d %H:%M") == "2027-07-14 09:15"
    assert slots[0][1].astimezone(zone).strftime("%Y-%m-%d %H:%M") == "2027-07-14 10:45"
    assert await service.find_free_slots(
        user,
        day=datetime(2027, 7, 13, 12),
        duration_minutes=30,
    ) == []


async def test_cancel_proposed_blocks_only_cancels_task_linked_work_blocks(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    task = await TaskService(db_session).create_task(user, title="Planned work")
    service = CalendarService(db_session)
    day = datetime(2027, 7, 14, 12, tzinfo=UTC)
    work_block = await service.create_internal_block(
        user,
        title="WorkBlock",
        start_at=day,
        end_at=day + timedelta(minutes=30),
        status=CalendarEventStatus.PROPOSED,
        source_task_id=task.id,
    )
    generic_event = await service.create_internal_block(
        user,
        title="Generic proposal",
        start_at=day + timedelta(hours=1),
        end_at=day + timedelta(hours=1, minutes=30),
        status=CalendarEventStatus.PROPOSED,
    )

    cancelled = await service.cancel_proposed_blocks(user, day=day)

    assert cancelled == 1
    assert work_block.status == CalendarEventStatus.CANCELLED
    assert generic_event.status == CalendarEventStatus.PROPOSED


async def test_generic_calendar_write_paths_take_the_user_lock(db_session, monkeypatch):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    task = await TaskService(db_session).create_task(user, title="Lock ordering")
    service = CalendarService(db_session)
    locked_user_ids = []

    async def record_lock(locked_user):
        locked_user_ids.append(locked_user.id)

    monkeypatch.setattr(service, "_lock_user", record_lock)
    starts_at = datetime(2027, 7, 14, 12, tzinfo=UTC)
    event = await service.create_internal_block(
        user,
        title="Generic write",
        start_at=starts_at,
        end_at=starts_at + timedelta(minutes=30),
    )
    await service.update_internal_event(user, event, title="Updated write")
    await service.cancel_internal_event(user, event)
    generic_proposal = await service.create_internal_block(
        user,
        title="Generic proposal",
        start_at=starts_at + timedelta(minutes=30),
        end_at=starts_at + timedelta(hours=1),
        status=CalendarEventStatus.PROPOSED,
    )
    await service.confirm_proposed_block(user, generic_proposal)
    proposed = await service.create_internal_block(
        user,
        title="Proposed work",
        start_at=starts_at + timedelta(hours=1),
        end_at=starts_at + timedelta(hours=1, minutes=30),
        status=CalendarEventStatus.PROPOSED,
        source_task_id=task.id,
    )
    await service.cancel_proposed_blocks(user, day=starts_at)
    external = await service.upsert_external_event(
        user,
        source=CalendarSource.GOOGLE,
        external_calendar_id="primary",
        external_event_id="lock-ordering",
        title="External write",
        start_at=starts_at + timedelta(hours=2),
        end_at=starts_at + timedelta(hours=2, minutes=30),
    )
    await service.reconcile_external_events(
        user,
        source=CalendarSource.GOOGLE,
        external_calendar_id="primary",
        start_at=external.start_at,
        end_at=external.end_at,
        seen_event_ids=set(),
    )

    assert generic_proposal.status == CalendarEventStatus.CONFIRMED
    assert proposed.status == CalendarEventStatus.CANCELLED
    assert external.status == CalendarEventStatus.CANCELLED
    assert locked_user_ids == [user.id] * 9
