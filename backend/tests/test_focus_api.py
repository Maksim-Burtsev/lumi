from __future__ import annotations

import asyncio
import calendar
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import event, select

from lumi.api.deps import get_current_user
from lumi.db.models import FocusSession, FocusSessionStatus, Task, UiEvent
from lumi.db.session import get_engine, session_scope
from lumi.main import app
from lumi.services.focus import FocusService
from lumi.services.projects import ProjectService
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
    assert session["project_name"] == "Lumi"
    assert session["project_id"] == str(task.project_id)
    assert session["local_date"] == datetime.now(get_zone(user.timezone)).date().isoformat()
    assert session["task"]["title"] == "Focus timer v1"

    duplicate = await client.post(
        "/api/focus/sessions",
        json={"intention": "Вторая сессия", "planned_minutes": 25},
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {"error": "active_focus_session_exists"}

    finish = await client.post(
        f"/api/focus/sessions/{session['id']}/finish",
        json={
            "accomplished_text": "Собрал структуру v1 и API контракты",
            "distraction_text": "",
            "next_step_text": "Нарисовать макеты и согласовать UX",
            "focus_score": 4,
        },
    )
    assert finish.status_code == 200
    finished = finish.json()["session"]
    assert finished["status"] == "completed"
    assert finished["duration_seconds"] >= 0
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
        "/api/focus/sessions/log",
        json={
            "project_name": "Lumi",
            "intention": "Проработать таймер",
            "logged_at": (datetime.now(UTC) - timedelta(minutes=35)).isoformat(),
            "duration_minutes": 30,
            "accomplished_text": "Сделал",
            "next_step_text": "Дальше",
            "focus_score": 5,
        },
    )
    assert first.status_code == 201

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
    assert body["total_focus_seconds"] == first.json()["session"]["duration_seconds"]
    assert body["project_breakdown"] == [
        {
            "project_id": first.json()["session"]["project_id"],
            "project_name": "Lumi",
            "project": "Lumi",
            "focus_seconds": first.json()["session"]["duration_seconds"],
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


async def test_focus_summary_includes_weekly_kpis_daypart_and_baseline_delta(client, db_session, monkeypatch):
    fixed_now = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    monkeypatch.setattr("lumi.services.focus.utc_now", lambda: fixed_now)
    now = fixed_now.replace(hour=7)
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
                "project_name": "Lumi",
                "intention": f"Reviewable session {index}",
                "logged_at": (datetime.now(UTC) - timedelta(hours=1, days=index)).isoformat(),
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
            "project_name": "QA Project",
            "accomplished_text": "Filled later",
            "distraction_text": "Slack",
            "next_step_text": "Retest",
            "focus_score": 5,
        },
    )
    assert patched.status_code == 200
    session = patched.json()["session"]
    assert session["intention"] == "Updated reviewable session"
    assert session["project_name"] == "QA Project"
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
    assert body["total_focus_delta_percent"] is None
    assert body["average_daily_focus_delta_percent"] is None
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
    assert invalid.status_code == 422
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


async def test_focus_month_summary_uses_calendar_month_days(client, monkeypatch):
    now = datetime(2026, 7, 15, 12, tzinfo=UTC)
    monkeypatch.setattr("lumi.services.focus.utc_now", lambda: now)
    response = await client.get("/api/focus/summary", params={"period": "month"})

    assert response.status_code == 200
    body = response.json()
    _, days_in_month = calendar.monthrange(now.year, now.month)
    assert len(body["daily_activity"]) == days_in_month
    assert body["daily_activity"][0]["date"] == datetime(now.year, now.month, 1).date().isoformat()
    assert (
        body["daily_activity"][-1]["date"] == datetime(now.year, now.month, days_in_month).date().isoformat()
    )


async def test_focus_delete_completed_session_updates_summary_and_forbids_active_or_other_user(
    client, db_session
):
    completed = await client.post(
        "/api/focus/sessions/log",
        json={
            "project": "Delete QA",
            "intention": "Delete me",
            "logged_at": (datetime.now(UTC) - timedelta(minutes=35)).isoformat(),
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


async def test_focus_patch_preserves_omitted_fields_and_explicit_null_clears(client, db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    task = await TaskService(db_session).create_task(user, title="Patch task", project="Patch project")
    await db_session.commit()
    logged = await client.post(
        "/api/focus/sessions/log",
        json={
            "task_id": str(task.id),
            "intention": "Original intention",
            "logged_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
            "duration_minutes": 45,
            "accomplished_text": "Accomplished",
            "distraction_text": "Notifications",
            "next_step_text": "Continue",
            "focus_score": 5,
        },
    )
    assert logged.status_code == 201
    session_id = logged.json()["session"]["id"]

    partial = await client.patch(
        f"/api/focus/sessions/{session_id}",
        json={"intention": "Changed only intention"},
    )
    assert partial.status_code == 200
    assert partial.json()["session"]["reflection"] == {
        "accomplished_text": "Accomplished",
        "distraction_text": "Notifications",
        "next_step_text": "Continue",
        "focus_score": 5,
    }
    assert partial.json()["session"]["task"]["id"] == str(task.id)
    assert partial.json()["session"]["project_id"] == str(task.project_id)

    cleared = await client.patch(
        f"/api/focus/sessions/{session_id}",
        json={
            "task_id": None,
            "project_id": None,
            "accomplished_text": None,
            "distraction_text": None,
            "next_step_text": None,
            "focus_score": None,
        },
    )
    assert cleared.status_code == 200
    body = cleared.json()["session"]
    assert body["task"] is None
    assert body["project_id"] is None
    assert body["project_name"] is None
    assert body["reflection"] == {
        "accomplished_text": None,
        "distraction_text": None,
        "next_step_text": None,
        "focus_score": None,
    }


async def test_focus_project_ownership_custom_project_and_snapshot(client, db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    other = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID + 1)
    foreign_project = await ProjectService(db_session).get_or_create(other, "Foreign")
    assert foreign_project is not None
    await db_session.commit()

    forbidden = await client.post(
        "/api/focus/sessions",
        json={
            "project_id": str(foreign_project.id),
            "intention": "Must not attach",
            "planned_minutes": 25,
        },
    )
    assert forbidden.status_code == 404
    assert forbidden.json() == {"error": "project_not_found"}

    created = await client.post(
        "/api/focus/sessions/log",
        json={
            "project_name": "Custom focus project",
            "intention": "Custom project session",
            "logged_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "duration_minutes": 25,
        },
    )
    assert created.status_code == 201
    body = created.json()["session"]
    assert body["project_id"] is not None
    assert body["project_name"] == "Custom focus project"

    project = await ProjectService(db_session).get(user, uuid.UUID(body["project_id"]))
    assert project is not None
    project.name = "Renamed project"
    await db_session.commit()
    fetched = await client.get(f"/api/focus/sessions/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["session"]["project_name"] == "Renamed project"
    stored = await db_session.get(FocusSession, uuid.UUID(body["id"]))
    assert stored is not None
    assert stored.project_snapshot == "Custom focus project"


async def test_focus_rejects_client_finish_time_and_invalid_manual_edit_times(client):
    active = await client.post(
        "/api/focus/sessions",
        json={"intention": "Server clock", "planned_minutes": 25},
    )
    assert active.status_code == 201
    rejected_finish = await client.post(
        f"/api/focus/sessions/{active.json()['session']['id']}/finish",
        json={"ended_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
    )
    assert rejected_finish.status_code == 422

    future_log = await client.post(
        "/api/focus/sessions/log",
        json={
            "intention": "Future block",
            "logged_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "duration_minutes": 25,
        },
    )
    assert future_log.status_code == 422
    assert future_log.json() == {"error": "focus_session_time_in_future"}

    await client.post(f"/api/focus/sessions/{active.json()['session']['id']}/abandon")
    logged = await client.post(
        "/api/focus/sessions/log",
        json={
            "intention": "Long edit",
            "logged_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
            "duration_minutes": 30,
        },
    )
    too_long = await client.patch(
        f"/api/focus/sessions/{logged.json()['session']['id']}",
        json={
            "started_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
            "ended_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        },
    )
    assert too_long.status_code == 422
    assert too_long.json() == {"error": "focus_session_duration_too_long"}


async def test_focus_start_and_finish_abandon_races_return_stable_conflicts(client):
    starts = await asyncio.gather(
        client.post(
            "/api/focus/sessions",
            json={
                "project_name": "Concurrent project",
                "intention": "Concurrent A",
                "planned_minutes": 25,
            },
        ),
        client.post(
            "/api/focus/sessions",
            json={
                "project_name": "Concurrent project",
                "intention": "Concurrent B",
                "planned_minutes": 25,
            },
        ),
    )
    assert sorted(response.status_code for response in starts) == [201, 409]
    session_id = next(response.json()["session"]["id"] for response in starts if response.status_code == 201)

    terminal = await asyncio.gather(
        client.post(f"/api/focus/sessions/{session_id}/finish", json={}),
        client.post(f"/api/focus/sessions/{session_id}/abandon"),
    )
    assert sorted(response.status_code for response in terminal) == [200, 409]
    assert next(response.json() for response in terminal if response.status_code == 409) == {
        "error": "focus_session_not_active"
    }


async def test_focus_history_server_search_filter_pagination_and_single_get(
    client,
    db_session,
    monkeypatch,
):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    project = await ProjectService(db_session).get_or_create(user, "History project")
    assert project is not None
    now = datetime(2026, 7, 15, 12, tzinfo=UTC)
    monkeypatch.setattr("lumi.services.focus.utc_now", lambda: now)
    rows = []
    for index in range(301):
        started = now - timedelta(hours=2, seconds=index)
        rows.append(
            FocusSession(
                user_id=user.id,
                project_id=project.id,
                project_snapshot=project.name,
                intention="Needle result" if index == 217 else f"History row {index}",
                planned_minutes=20,
                status=FocusSessionStatus.COMPLETED,
                started_at=started,
                target_end_at=started + timedelta(minutes=20),
                ended_at=started + timedelta(minutes=20),
                duration_seconds=1200,
            )
        )
    db_session.add_all(rows)
    await db_session.commit()

    project_summary = await client.get(
        "/api/focus/summary",
        params={"period": "month", "project_id": str(project.id)},
    )
    assert project_summary.status_code == 200
    assert project_summary.json()["total_sessions"] == 301
    assert project_summary.json()["total_focus_seconds"] == 301 * 1200

    search_summary = await client.get(
        "/api/focus/summary",
        params={"period": "month", "q": "needle"},
    )
    assert search_summary.status_code == 200
    assert search_summary.json()["total_sessions"] == 1
    assert search_summary.json()["total_focus_seconds"] == 1200

    first = await client.get(
        "/api/focus/sessions",
        params={"period": "month", "project_id": str(project.id), "limit": 300},
    )
    assert first.status_code == 200
    assert len(first.json()["items"]) == 300
    assert first.json()["has_more"] is True
    assert first.json()["next_offset"] == 300
    second = await client.get(
        "/api/focus/sessions",
        params={
            "period": "month",
            "project_id": str(project.id),
            "limit": 300,
            "offset": 300,
        },
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1
    assert second.json()["has_more"] is False

    search = await client.get(
        "/api/focus/sessions",
        params={"period": "month", "q": "needle", "limit": 20},
    )
    assert search.status_code == 200
    assert [item["intention"] for item in search.json()["items"]] == ["Needle result"]
    fetched = await client.get(f"/api/focus/sessions/{rows[217].id}")
    assert fetched.status_code == 200
    assert fetched.json()["session"]["intention"] == "Needle result"

    statements: list[str] = []

    def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", count_selects)
    try:
        complete_summary = await FocusService(db_session).summary(
            user,
            period="month",
            project_id=project.id,
        )
    finally:
        event.remove(engine, "before_cursor_execute", count_selects)
    assert complete_summary.total_sessions == 301
    assert len(statements) <= 7


async def test_focus_summary_searches_all_history_fields_and_keeps_joins_owned(
    client,
    db_session,
    monkeypatch,
):
    now = datetime(2026, 7, 15, 12, tzinfo=UTC)
    monkeypatch.setattr("lumi.services.focus.utc_now", lambda: now)
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    current_project = await ProjectService(db_session).get_or_create(
        user,
        "needle-current-project-881",
    )
    task = await TaskService(db_session).create_task(
        user,
        title="needle-task-title-881",
        project="History search",
    )
    other_user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID + 881)
    foreign_project = await ProjectService(db_session).get_or_create(
        other_user,
        "foreign-secret-project-881",
    )
    assert current_project is not None
    assert foreign_project is not None

    base = datetime(2026, 7, 14, 9, tzinfo=UTC)

    def completed(**values) -> FocusSession:
        started = base + timedelta(minutes=len(rows_for_search) * 30)
        intention = values.pop("intention", "ordinary history row")
        return FocusSession(
            user_id=user.id,
            intention=intention,
            planned_minutes=20,
            status=FocusSessionStatus.COMPLETED,
            started_at=started,
            target_end_at=started + timedelta(minutes=20),
            ended_at=started + timedelta(minutes=20),
            duration_seconds=1200,
            **values,
        )

    rows_for_search: list[FocusSession] = []
    rows_for_search.extend(
        [
            completed(intention="needle-intention-881"),
            completed(accomplished_text="needle-accomplished-881"),
            completed(distraction_text="needle-distraction-881"),
            completed(next_step_text="needle-next-step-881"),
            completed(project_snapshot="needle-snapshot-881"),
            completed(
                project_id=current_project.id,
                project_snapshot="previous project name",
            ),
            completed(task_id=task.id),
            # Deliberately inconsistent legacy data must not expose another user's
            # current project name through either search or project filtering.
            completed(project_id=foreign_project.id),
        ]
    )
    db_session.add_all(rows_for_search)
    await db_session.commit()

    for query in (
        "needle-intention-881",
        "needle-accomplished-881",
        "needle-distraction-881",
        "needle-next-step-881",
        "needle-snapshot-881",
        "needle-current-project-881",
        "needle-task-title-881",
    ):
        response = await client.get(
            "/api/focus/summary",
            params={
                "period": "custom",
                "from_date": "2026-07-14",
                "to_date": "2026-07-14",
                "q": query,
            },
        )
        assert response.status_code == 200
        assert response.json()["total_sessions"] == 1
        assert len(response.json()["daily_activity"]) == 1

    owned_project = await client.get(
        "/api/focus/summary",
        params={
            "period": "custom",
            "from_date": "2026-07-14",
            "to_date": "2026-07-14",
            "project_id": str(current_project.id),
        },
    )
    assert owned_project.status_code == 200
    assert owned_project.json()["total_sessions"] == 1

    foreign_search = await client.get(
        "/api/focus/summary",
        params={
            "period": "custom",
            "from_date": "2026-07-14",
            "to_date": "2026-07-14",
            "q": "foreign-secret-project-881",
        },
    )
    assert foreign_search.status_code == 200
    assert foreign_search.json()["total_sessions"] == 0

    foreign_filter = await client.get(
        "/api/focus/summary",
        params={
            "period": "custom",
            "from_date": "2026-07-14",
            "to_date": "2026-07-14",
            "project_id": str(foreign_project.id),
        },
    )
    assert foreign_filter.status_code == 200
    assert foreign_filter.json()["total_sessions"] == 0


async def test_focus_state_has_bounded_query_count_without_task_n_plus_one(client, db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    tasks = [
        await TaskService(db_session).create_task(user, title=f"Bounded query {index}", project="Query")
        for index in range(10)
    ]
    now = datetime.now(UTC)
    for index, task in enumerate(tasks):
        started = now - timedelta(hours=2, minutes=index)
        db_session.add(
            FocusSession(
                user_id=user.id,
                task_id=task.id,
                project_id=task.project_id,
                project_snapshot=task.project,
                intention=f"Query row {index}",
                planned_minutes=20,
                status=FocusSessionStatus.COMPLETED,
                started_at=started,
                target_end_at=started + timedelta(minutes=20),
                ended_at=started + timedelta(minutes=20),
                duration_seconds=1200,
            )
        )
    await db_session.commit()

    statements: list[str] = []

    def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", count_selects)
    try:
        response = await client.get("/api/focus/state")
    finally:
        event.remove(engine, "before_cursor_execute", count_selects)
    assert response.status_code == 200
    assert len(response.json()["recent_sessions"]) == 10
    assert len(statements) <= 9


async def test_focus_mutations_emit_realtime_focus_topic(client, db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    await db_session.commit()
    logged = await client.post(
        "/api/focus/sessions/log",
        json={
            "intention": "Realtime logged",
            "logged_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "duration_minutes": 25,
        },
    )
    logged_id = logged.json()["session"]["id"]
    await client.patch(f"/api/focus/sessions/{logged_id}", json={"focus_score": 4})
    await client.delete(f"/api/focus/sessions/{logged_id}")
    active = await client.post(
        "/api/focus/sessions",
        json={"intention": "Realtime active", "planned_minutes": 25},
    )
    await client.post(f"/api/focus/sessions/{active.json()['session']['id']}/abandon")
    finished = await client.post(
        "/api/focus/sessions",
        json={"intention": "Realtime finish", "planned_minutes": 25},
    )
    await client.post(f"/api/focus/sessions/{finished.json()['session']['id']}/finish", json={})

    await db_session.rollback()
    events = list(
        (
            await db_session.execute(select(UiEvent).where(UiEvent.user_id == user.id).order_by(UiEvent.id))
        ).scalars()
    )
    focus_events = [event for event in events if "focus" in event.topics]
    assert [event.event_type for event in focus_events] == [
        "focus.logged",
        "focus.updated",
        "focus.deleted",
        "focus.started",
        "focus.abandoned",
        "focus.started",
        "focus.finished",
    ]


async def test_focus_period_bounds_are_dst_safe_and_local_date_is_server_owned(
    client,
    db_session,
    monkeypatch,
):
    fixed_now = datetime(2026, 3, 30, 12, tzinfo=UTC)
    monkeypatch.setattr("lumi.services.focus.utc_now", lambda: fixed_now)
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    user.timezone = "Europe/Berlin"
    await db_session.commit()
    start, end, days = FocusService(db_session).period_bounds(user, "week")
    assert days == 7
    assert end - start == timedelta(hours=167)

    response = await client.post(
        "/api/focus/sessions/log",
        json={
            "intention": "Near midnight",
            "logged_at": "2026-03-28T23:30:00+00:00",
            "duration_minutes": 20,
        },
    )
    assert response.status_code == 201
    assert response.json()["session"]["local_date"] == "2026-03-29"


async def test_focus_month_to_date_uses_elapsed_days_and_matching_prior_months(
    db_session,
    monkeypatch,
):
    fixed_now = datetime(2026, 7, 12, 12, tzinfo=UTC)
    monkeypatch.setattr("lumi.services.focus.utc_now", lambda: fixed_now)
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    user.timezone = "UTC"
    for day in range(1, 13):
        started = datetime(2026, 7, day, 9, tzinfo=UTC)
        db_session.add(
            FocusSession(
                user_id=user.id,
                intention=f"Current {day}",
                planned_minutes=60,
                status=FocusSessionStatus.COMPLETED,
                started_at=started,
                target_end_at=started + timedelta(hours=1),
                ended_at=started + timedelta(hours=1),
                duration_seconds=3600,
            )
        )
    for month in range(3, 7):
        for day in range(1, 13):
            started = datetime(2026, month, day, 9, tzinfo=UTC)
            db_session.add(
                FocusSession(
                    user_id=user.id,
                    intention=f"Baseline {month}-{day}",
                    planned_minutes=30,
                    status=FocusSessionStatus.COMPLETED,
                    started_at=started,
                    target_end_at=started + timedelta(minutes=30),
                    ended_at=started + timedelta(minutes=30),
                    duration_seconds=1800,
                )
            )
    await db_session.flush()
    summary = await FocusService(db_session).summary(user, period="month")
    assert len(summary.daily_activity) == 31
    assert summary.total_focus_seconds == 12 * 3600
    assert summary.average_daily_focus_seconds == 3600
    assert summary.total_focus_delta_percent == 100
    assert summary.average_daily_focus_delta_percent == 100


async def test_focus_demo_seed_rejects_non_local_environment(monkeypatch):
    from lumi.scripts import seed_focus_demo

    monkeypatch.setattr(
        seed_focus_demo,
        "get_settings",
        lambda: SimpleNamespace(is_local=False, allowed_telegram_user_ids=[TEST_TELEGRAM_ID]),
    )
    with pytest.raises(RuntimeError, match="APP_ENV=local"):
        await seed_focus_demo.seed()


async def test_focus_seeds_preserve_user_rows_and_replace_only_marked_demo_rows(monkeypatch):
    from lumi.scripts import seed_focus_demo, seed_local

    settings = SimpleNamespace(is_local=True, allowed_telegram_user_ids=[TEST_TELEGRAM_ID])
    monkeypatch.setattr(seed_local, "get_settings", lambda: settings)
    monkeypatch.setattr(seed_focus_demo, "get_settings", lambda: settings)
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task_service = TaskService(session)
        stale_demo_task = await task_service.create_task(
            user,
            title="Removed from demo manifest",
            project="Demo cleanup",
            source="seed_focus_demo",
            created_by="system",
            actor="system",
        )
        stale_demo_task.metadata_ = {"seed_batch_id": str(seed_focus_demo.FOCUS_DEMO_SEED_BATCH_ID)}
        linked_demo_task = await task_service.create_task(
            user,
            title="Removed but adopted by user",
            project="Demo cleanup",
            source="seed_focus_demo",
            created_by="system",
            actor="system",
        )
        linked_demo_task.metadata_ = {"seed_batch_id": str(seed_focus_demo.FOCUS_DEMO_SEED_BATCH_ID)}
        await task_service.create_task(
            user,
            title="Unmarked user-owned task",
            project="Demo cleanup",
            source="seed_focus_demo",
        )
        started = datetime.now(UTC) - timedelta(hours=2)
        session.add_all(
            [
                FocusSession(
                    user_id=user.id,
                    task_id=linked_demo_task.id,
                    project_id=linked_demo_task.project_id,
                    project_snapshot=linked_demo_task.project,
                    intention="User kept a former demo task",
                    planned_minutes=25,
                    status=FocusSessionStatus.COMPLETED,
                    started_at=started - timedelta(hours=1),
                    target_end_at=started - timedelta(minutes=35),
                    ended_at=started - timedelta(minutes=35),
                    duration_seconds=1500,
                ),
                FocusSession(
                    user_id=user.id,
                    intention="Write product spec",
                    planned_minutes=30,
                    status=FocusSessionStatus.COMPLETED,
                    started_at=started,
                    target_end_at=started + timedelta(minutes=30),
                    ended_at=started + timedelta(minutes=30),
                    duration_seconds=1800,
                    accomplished_text="Moved the feature forward and captured follow-up notes.",
                    next_step_text="Run browser QA.",
                ),
            ]
        )

    await seed_local.seed()
    await seed_focus_demo.seed()
    await seed_focus_demo.seed()

    async with session_scope() as session:
        focus_rows = list(
            (await session.execute(select(FocusSession).where(FocusSession.user_id.is_not(None)))).scalars()
        )
        demo_tasks = list(
            (await session.execute(select(Task).where(Task.source == "seed_focus_demo"))).scalars()
        )
    assert len([row for row in focus_rows if row.seed_batch_id is None]) == 2
    assert (
        len([row for row in focus_rows if row.seed_batch_id == seed_focus_demo.FOCUS_DEMO_SEED_BATCH_ID])
        == 100
    )
    tasks_by_title = {task.title: task for task in demo_tasks}
    assert "Removed from demo manifest" not in tasks_by_title
    assert "Removed but adopted by user" in tasks_by_title
    assert "Unmarked user-owned task" in tasks_by_title
    current_seed_tasks = [
        task
        for task in demo_tasks
        if task.title in {title for title, *_ in seed_focus_demo.SEED_TASKS}
        and task.metadata_.get("seed_batch_id") == str(seed_focus_demo.FOCUS_DEMO_SEED_BATCH_ID)
    ]
    assert len(current_seed_tasks) == len(seed_focus_demo.SEED_TASKS)
