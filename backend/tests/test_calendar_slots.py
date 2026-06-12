from datetime import UTC, datetime, timedelta

from lumi.services.calendar import merge_busy_intervals, subtract_intervals


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
