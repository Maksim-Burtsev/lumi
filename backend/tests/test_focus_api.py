from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from lumi.api.deps import get_current_user
from lumi.db.models import FocusSession, FocusSessionStatus
from lumi.db.session import session_scope
from lumi.main import app
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.utils.time import get_zone

from .conftest import TEST_TELEGRAM_ID


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.fixture
async def client(user):
    async def _override_user():
        async with session_scope() as session:
            return await UserService(session).ensure_user(TEST_TELEGRAM_ID)

    app.dependency_overrides[get_current_user] = _override_user
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_focus_session_lifecycle_tracks_task_project_and_reflection(client, db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    task = await TaskService(db_session).create_task(
        user,
        title="Focus timer v1",
        project="Lumi",
    )
    await db_session.commit()

    start = await client.post(
        "/api/focus/sessions",
        json={
            "task_id": str(task.id),
            "intention": "Написать черновик спецификации",
            "planned_minutes": 45,
        },
    )
    assert start.status_code == 201
    session = start.json()["session"]
    assert session["status"] == "active"
    assert session["project"] == "Lumi"
    assert session["task"]["title"] == "Focus timer v1"

    duplicate = await client.post(
        "/api/focus/sessions",
        json={"intention": "Вторая сессия", "planned_minutes": 25},
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {"error": "active_focus_session_exists"}

    ended_at = datetime.now(UTC) + timedelta(minutes=49)
    finish = await client.post(
        f"/api/focus/sessions/{session['id']}/finish",
        json={
            "ended_at": ended_at.isoformat(),
            "accomplished_text": "Собрал структуру v1 и API контракты",
            "distraction_text": "",
            "next_step_text": "Нарисовать макеты и согласовать UX",
            "focus_score": 4,
        },
    )
    assert finish.status_code == 200
    finished = finish.json()["session"]
    assert finished["status"] == "completed"
    assert finished["duration_seconds"] > 45 * 60
    assert finished["reflection"]["focus_score"] == 4

    state = await client.get("/api/focus/state")
    assert state.status_code == 200
    body = state.json()
    assert body["active_session"] is None
    assert body["today"]["completed_sessions"] == 1
    assert body["today"]["focus_seconds"] == finished["duration_seconds"]
    assert body["recent_sessions"][0]["id"] == finished["id"]


async def test_focus_summary_groups_by_project_and_ignores_abandoned(client, db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)

    first = await client.post(
        "/api/focus/sessions",
        json={"project": "Lumi", "intention": "Проработать таймер", "planned_minutes": 25},
    )
    assert first.status_code == 201
    first_id = first.json()["session"]["id"]
    finish = await client.post(
        f"/api/focus/sessions/{first_id}/finish",
        json={
            "ended_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
            "accomplished_text": "Сделал",
            "distraction_text": "",
            "next_step_text": "Дальше",
            "focus_score": 5,
        },
    )
    assert finish.status_code == 200

    second = await client.post(
        "/api/focus/sessions",
        json={"project": "Work", "intention": "Отвлекся", "planned_minutes": 25},
    )
    assert second.status_code == 201
    abandon = await client.post(f"/api/focus/sessions/{second.json()['session']['id']}/abandon")
    assert abandon.status_code == 200

    summary = await client.get("/api/focus/summary", params={"period": "week"})
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_sessions"] == 1
    assert body["total_focus_seconds"] == finish.json()["session"]["duration_seconds"]
    assert body["project_breakdown"] == [
        {
            "project": "Lumi",
            "focus_seconds": finish.json()["session"]["duration_seconds"],
            "session_count": 1,
        }
    ]
    assert body["streak_days"] == 1
    assert body["daily_activity"][-1]["date"] == datetime.now(get_zone(user.timezone)).date().isoformat()


async def test_focus_manual_log_creates_completed_session_without_active_timer(client, db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    task = await TaskService(db_session).create_task(
        user,
        title="Перенести дизайн Focus",
        project="Lumi",
    )
    await db_session.commit()

    logged_at = datetime.now(UTC) - timedelta(hours=1)
    response = await client.post(
        "/api/focus/sessions/log",
        json={
            "task_id": str(task.id),
            "project": "Lumi",
            "intention": "Сверстал макет в другом таймере",
            "logged_at": logged_at.isoformat(),
            "duration_minutes": 37,
            "accomplished_text": "Проверил minimal console",
            "distraction_text": "Нативный select мешал",
            "next_step_text": "Запустить browser QA",
            "focus_score": 5,
        },
    )

    assert response.status_code == 201
    session = response.json()["session"]
    assert session["status"] == "completed"
    assert session["task"]["title"] == "Перенести дизайн Focus"
    assert session["planned_minutes"] == 37
    assert session["duration_seconds"] == 37 * 60
    assert parse_iso(session["started_at"]) == logged_at
    assert parse_iso(session["ended_at"]) == logged_at + timedelta(minutes=37)
    assert session["reflection"]["focus_score"] == 5

    state = await client.get("/api/focus/state")
    body = state.json()
    assert body["active_session"] is None
    assert body["today"]["completed_sessions"] == 1
    assert body["recent_sessions"][0]["id"] == session["id"]


async def test_focus_summary_includes_weekly_kpis_daypart_and_baseline_delta(client, db_session):
    now = datetime.now(UTC).replace(hour=7, minute=0, second=0, microsecond=0)
    current_week = [
        (now - timedelta(days=6), 60, "Morning build"),
        (now - timedelta(days=5), 60, "Morning QA"),
        (now - timedelta(days=4), 60, "Morning design"),
        (now - timedelta(days=3), 60, "Morning polish"),
        (now - timedelta(days=2), 60, "Morning review"),
        (now - timedelta(days=1), 60, "Morning docs"),
        (now, 60, "Morning ship"),
    ]
    baseline_weeks = []
    for week in range(1, 5):
        baseline_weeks.extend(
            [
                (now - timedelta(days=7 * week + offset), 30, f"Baseline {week}-{offset}")
                for offset in range(7)
            ]
        )

    for started, minutes, title in [*current_week, *baseline_weeks]:
        response = await client.post(
            "/api/focus/sessions/log",
            json={
                "project": "Lumi",
                "intention": title,
                "logged_at": started.isoformat(),
                "duration_minutes": minutes,
                "focus_score": 4,
            },
        )
        assert response.status_code == 201

    summary = await client.get("/api/focus/summary", params={"period": "week"})
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_focus_seconds"] == 7 * 60 * 60
    assert body["average_daily_focus_seconds"] == 60 * 60
    assert body["total_focus_delta_percent"] == 100
    assert body["average_daily_focus_delta_percent"] == 100
    assert body["most_focused_daypart"] == "morning"
    assert body["daypart_breakdown"][0] == {"daypart": "morning", "focus_seconds": 7 * 60 * 60}


async def test_focus_sessions_list_and_patch_completed_review(client):
    created_ids: list[str] = []
    for index in range(3):
        response = await client.post(
            "/api/focus/sessions/log",
            json={
                "project": "Lumi",
                "intention": f"Reviewable session {index}",
                "logged_at": (datetime.now(UTC) - timedelta(days=index)).isoformat(),
                "duration_minutes": 25 + index,
            },
        )
        assert response.status_code == 201
        created_ids.append(response.json()["session"]["id"])

    listed = await client.get("/api/focus/sessions", params={"period": "month", "limit": 2})
    assert listed.status_code == 200
    body = listed.json()
    assert [item["id"] for item in body["items"]] == created_ids[:2]

    patched = await client.patch(
        f"/api/focus/sessions/{created_ids[0]}",
        json={
            "intention": "Updated reviewable session",
            "project": "QA Project",
            "accomplished_text": "Filled later",
            "distraction_text": "Slack",
            "next_step_text": "Retest",
            "focus_score": 5,
        },
    )
    assert patched.status_code == 200
    session = patched.json()["session"]
    assert session["intention"] == "Updated reviewable session"
    assert session["project"] == "QA Project"
    assert session["reflection"] == {
        "accomplished_text": "Filled later",
        "distraction_text": "Slack",
        "next_step_text": "Retest",
        "focus_score": 5,
    }


async def test_focus_custom_range_filters_daily_activity_sessions_and_paginates(client):
    records = [
        ("Lumi", "Custom first", datetime(2026, 6, 10, 9, 0, tzinfo=UTC), 40),
        ("QA Project", "Custom second", datetime(2026, 6, 12, 11, 0, tzinfo=UTC), 55),
        ("Outside", "Outside range", datetime(2026, 6, 20, 11, 0, tzinfo=UTC), 90),
    ]
    for project, intention, logged_at, duration in records:
        response = await client.post(
            "/api/focus/sessions/log",
            json={
                "project": project,
                "intention": intention,
                "logged_at": logged_at.isoformat(),
                "duration_minutes": duration,
                "focus_score": 4,
            },
        )
        assert response.status_code == 201

    summary = await client.get(
        "/api/focus/summary",
        params={"period": "custom", "from_date": "2026-06-10", "to_date": "2026-06-12"},
    )
    assert summary.status_code == 200
    body = summary.json()
    assert body["period"] == "custom"
    assert body["total_sessions"] == 2
    assert body["total_focus_seconds"] == (40 + 55) * 60
    assert [item["date"] for item in body["daily_activity"]] == [
        "2026-06-10",
        "2026-06-11",
        "2026-06-12",
    ]
    assert [item["project"] for item in body["project_breakdown"]] == ["QA Project", "Lumi"]

    first_page = await client.get(
        "/api/focus/sessions",
        params={
            "period": "custom",
            "from_date": "2026-06-10",
            "to_date": "2026-06-12",
            "limit": 1,
            "offset": 0,
        },
    )
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert [item["intention"] for item in first_body["items"]] == ["Custom second"]
    assert first_body["has_more"] is True
    assert first_body["next_offset"] == 1

    second_page = await client.get(
        "/api/focus/sessions",
        params={
            "period": "custom",
            "from_date": "2026-06-10",
            "to_date": "2026-06-12",
            "limit": 1,
            "offset": 1,
        },
    )
    assert second_page.status_code == 200
    second_body = second_page.json()
    assert [item["intention"] for item in second_body["items"]] == ["Custom first"]
    assert second_body["has_more"] is False
    assert second_body["next_offset"] is None


async def test_focus_patch_completed_session_time_updates_duration_and_rejects_invalid_or_active(client):
    logged = await client.post(
        "/api/focus/sessions/log",
        json={
            "project": "Time edit",
            "intention": "Editable time",
            "logged_at": datetime(2026, 6, 16, 10, 0, tzinfo=UTC).isoformat(),
            "duration_minutes": 30,
        },
    )
    assert logged.status_code == 201
    session_id = logged.json()["session"]["id"]

    patched = await client.patch(
        f"/api/focus/sessions/{session_id}",
        json={
            "started_at": datetime(2026, 6, 16, 12, 0, tzinfo=UTC).isoformat(),
            "ended_at": datetime(2026, 6, 16, 13, 15, tzinfo=UTC).isoformat(),
        },
    )
    assert patched.status_code == 200
    body = patched.json()["session"]
    assert parse_iso(body["started_at"]) == datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
    assert parse_iso(body["ended_at"]) == datetime(2026, 6, 16, 13, 15, tzinfo=UTC)
    assert body["duration_seconds"] == 75 * 60

    invalid = await client.patch(
        f"/api/focus/sessions/{session_id}",
        json={
            "started_at": datetime(2026, 6, 16, 14, 0, tzinfo=UTC).isoformat(),
            "ended_at": datetime(2026, 6, 16, 13, 0, tzinfo=UTC).isoformat(),
        },
    )
    assert invalid.status_code == 409
    assert invalid.json() == {"error": "invalid_focus_session_time"}

    active = await client.post(
        "/api/focus/sessions",
        json={"project": "Time edit", "intention": "Active time", "planned_minutes": 25},
    )
    assert active.status_code == 201
    active_patch = await client.patch(
        f"/api/focus/sessions/{active.json()['session']['id']}",
        json={"ended_at": datetime(2026, 6, 16, 13, 15, tzinfo=UTC).isoformat()},
    )
    assert active_patch.status_code == 409
    assert active_patch.json() == {"error": "focus_session_not_completed"}


async def test_focus_month_summary_uses_calendar_month_days(client):
    now = datetime.now(UTC)
    response = await client.get("/api/focus/summary", params={"period": "month"})

    assert response.status_code == 200
    body = response.json()
    _, days_in_month = calendar.monthrange(now.year, now.month)
    assert len(body["daily_activity"]) == days_in_month
    assert body["daily_activity"][0]["date"] == datetime(now.year, now.month, 1).date().isoformat()
    assert body["daily_activity"][-1]["date"] == datetime(now.year, now.month, days_in_month).date().isoformat()


async def test_focus_delete_completed_session_updates_summary_and_forbids_active_or_other_user(client, db_session):
    completed = await client.post(
        "/api/focus/sessions/log",
        json={
            "project": "Delete QA",
            "intention": "Delete me",
            "logged_at": datetime.now(UTC).isoformat(),
            "duration_minutes": 30,
        },
    )
    assert completed.status_code == 201
    completed_id = completed.json()["session"]["id"]

    before = await client.get("/api/focus/summary", params={"period": "week"})
    assert before.status_code == 200
    assert before.json()["total_focus_seconds"] >= 30 * 60

    delete_completed = await client.delete(f"/api/focus/sessions/{completed_id}")
    assert delete_completed.status_code == 204

    after = await client.get("/api/focus/summary", params={"period": "week"})
    assert after.status_code == 200
    assert after.json()["total_focus_seconds"] == before.json()["total_focus_seconds"] - 30 * 60

    active = await client.post(
        "/api/focus/sessions",
        json={"project": "Delete QA", "intention": "Active cannot delete", "planned_minutes": 25},
    )
    assert active.status_code == 201
    delete_active = await client.delete(f"/api/focus/sessions/{active.json()['session']['id']}")
    assert delete_active.status_code == 409
    assert delete_active.json() == {"error": "focus_session_active"}

    other_user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID + 100)
    other_session = FocusSession(
        user_id=other_user.id,
        intention="Other user",
        planned_minutes=15,
        status=FocusSessionStatus.COMPLETED,
        started_at=datetime.now(UTC) - timedelta(minutes=20),
        target_end_at=datetime.now(UTC) - timedelta(minutes=5),
        ended_at=datetime.now(UTC) - timedelta(minutes=5),
        duration_seconds=15 * 60,
    )
    db_session.add(other_session)
    await db_session.commit()

    delete_other = await client.delete(f"/api/focus/sessions/{other_session.id}")
    assert delete_other.status_code == 404
