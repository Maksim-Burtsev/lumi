from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from lumi.api.deps import get_current_user
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
