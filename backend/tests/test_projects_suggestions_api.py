from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from lumi.api.deps import get_current_user
from lumi.db.models import (
    AssistantOpportunityJob,
    AssistantSuggestionStatus,
    CalendarEvent,
    CalendarEventStatus,
    CalendarSource,
    Project,
    Task,
)
from lumi.db.session import session_scope
from lumi.main import app
from lumi.services import today as today_module
from lumi.services.assistant_suggestions import AssistantSuggestionService
from lumi.services.calendar import CalendarService
from lumi.services.users import UserService
from lumi.utils.time import utc_now

from .conftest import TEST_TELEGRAM_ID


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


async def test_projects_list_groups_open_tasks_and_returns_next_action(client):
    await client.post("/api/tasks", json={
        "title": "Сверить договор перед звонком",
        "project": "Alpha launch",
        "priority": "high",
    })
    await client.post("/api/tasks", json={
        "title": "Ответить Ивану по смете",
        "project": "Клиенты",
        "priority": "medium",
    })
    await client.post("/api/tasks", json={
        "title": "Проверить 3 аккаунт почты",
        "project": "Alpha launch",
        "priority": "low",
    })

    response = await client.get("/api/projects")

    assert response.status_code == 200
    items = response.json()["items"]
    alpha = next(item for item in items if item["name"] == "Alpha launch")
    assert alpha["active_task_count"] == 2
    assert alpha["next_task"]["title"] == "Сверить договор перед звонком"
    assert alpha["completed_task_count"] == 0
    assert alpha["health_status"] == "moving"
    assert alpha["health_reason"]


async def test_projects_list_does_not_create_system_backlog_project(client):
    response = await client.get("/api/projects")

    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_default_unscheduled_task_stays_unassigned_in_inbox(client):
    created = await client.post("/api/tasks", json={"title": "Raw idea"})

    assert created.status_code == 201
    task = created.json()["task"]
    assert task["status"] == "inbox"
    assert task["bucket"] == "inbox"
    assert task["project"] is None
    assert task["project_id"] is None

    projects = (await client.get("/api/projects")).json()["items"]
    assert projects == []


async def test_projects_list_sorts_attention_before_moving(client):
    await client.post("/api/tasks", json={
        "title": "Extend tool pool",
        "project": "Work",
        "priority": "medium",
    })
    await client.post("/api/tasks", json={
        "title": "Compare Mira design",
        "project": "Lumi",
        "priority": "high",
        "estimated_minutes": 45,
    })

    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        work = (await session.execute(select(Project).where(Project.user_id == user.id, Project.name == "Work"))).scalar_one()
        lumi = (await session.execute(select(Project).where(Project.user_id == user.id, Project.name == "Lumi"))).scalar_one()
        work.updated_at = utc_now() - timedelta(days=5)
        lumi.updated_at = utc_now()
        task = (await session.execute(select(Task).where(Task.user_id == user.id, Task.project_id == work.id))).scalar_one()
        task.updated_at = utc_now() - timedelta(days=5)

    response = await client.get("/api/projects")

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["name"] == "Work"
    assert items[0]["health_status"] == "needs_attention"
    assert "Quiet" in items[0]["health_reason"]
    assert items[1]["name"] == "Lumi"
    assert items[1]["health_status"] == "moving"


async def test_tasks_can_be_filtered_by_project_id(client):
    await client.post("/api/tasks", json={
        "title": "Extend tool pool",
        "project": "Work",
    })
    await client.post("/api/tasks", json={
        "title": "Compare Mira design",
        "project": "Lumi",
    })
    projects = (await client.get("/api/projects")).json()["items"]
    work = next(item for item in projects if item["name"] == "Work")

    response = await client.get("/api/tasks", params={"project_id": work["id"], "filter": "all"})

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["Extend tool pool"]


async def test_free_slots_api_allows_micro_slot_duration(client):
    response = await client.get("/api/calendar/free-slots", params={
        "date": "2026-06-10",
        "duration": 5,
    })

    assert response.status_code == 200
    assert response.json()["items"]


async def test_calendar_changes_enqueue_task_suggestion_refresh(client):
    response = await client.post("/api/calendar/events", json={
        "title": "Созвон",
        "start_at": "2026-06-10T10:00:00+00:00",
        "end_at": "2026-06-10T10:30:00+00:00",
    })

    assert response.status_code == 201
    event_id = response.json()["event"]["id"]
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        result = await session.execute(
            select(AssistantOpportunityJob).where(
                AssistantOpportunityJob.user_id == user.id,
                AssistantOpportunityJob.kind == "slot_suggestions",
                AssistantOpportunityJob.scope_key == "today",
            )
        )
        job = result.scalar_one()
        assert job.reason == "calendar_event.created"
        assert job.next_check_at is not None

    deleted = await client.delete(f"/api/calendar/events/{event_id}")

    assert deleted.status_code == 200
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        result = await session.execute(
            select(AssistantOpportunityJob).where(
                AssistantOpportunityJob.user_id == user.id,
                AssistantOpportunityJob.kind == "slot_suggestions",
                AssistantOpportunityJob.scope_key == "today",
            )
        )
        job = result.scalar_one()
        assert job.reason == "calendar_event.cancelled"


async def test_work_block_api_creates_and_confirms_idempotently(client):
    task = await client.post("/api/tasks", json={"title": "Write launch notes"})
    task_id = task.json()["task"]["id"]

    created = await client.post(
        "/api/calendar/work-blocks",
        json={
            "task_id": task_id,
            "start_at": "2035-07-11T10:00:00+03:00",
            "end_at": "2035-07-11T11:00:00+03:00",
            "status": "proposed",
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert set(body) == {"status", "reason", "event", "conflict_event_id"}
    assert body["status"] == "proposed"
    assert body["reason"] is None
    assert body["conflict_event_id"] is None
    assert body["event"]["kind"] == "work_block"
    assert body["event"]["title"] == "Write launch notes"
    assert body["event"]["source_task_id"] == task_id

    stale = await client.post(
        f"/api/calendar/work-blocks/{body['event']['id']}/confirm",
        json={"expected_updated_at": "2035-07-11T09:00:00+00:00"},
    )
    assert stale.status_code == 409
    assert stale.json()["status"] == "stale"
    assert stale.json()["reason"] == "proposal_changed"

    confirmed = await client.post(f"/api/calendar/work-blocks/{body['event']['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["event"]["status"] == "confirmed"

    repeated = await client.post(f"/api/calendar/work-blocks/{body['event']['id']}/confirm")
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "already_confirmed"


async def test_work_block_api_returns_structured_not_found_invalid_and_conflict(client):
    missing = await client.post(
        "/api/calendar/work-blocks",
        json={
            "task_id": "00000000-0000-0000-0000-000000000001",
            "title": "Missing task",
            "start_at": "2035-07-11T10:00:00+03:00",
            "end_at": "2035-07-11T11:00:00+03:00",
        },
    )
    assert missing.status_code == 404
    assert missing.json() == {
        "status": "not_found",
        "reason": "task_not_found",
        "event": None,
        "conflict_event_id": None,
    }

    first_task = await client.post("/api/tasks", json={"title": "First block"})
    first = await client.post(
        "/api/calendar/work-blocks",
        json={
            "task_id": first_task.json()["task"]["id"],
            "title": "First block",
            "start_at": "2035-07-11T10:00:00+03:00",
            "end_at": "2035-07-11T11:00:00+03:00",
            "status": "confirmed",
        },
    )
    assert first.status_code == 201

    second_task = await client.post("/api/tasks", json={"title": "Second block"})
    conflict = await client.post(
        "/api/calendar/work-blocks",
        json={
            "task_id": second_task.json()["task"]["id"],
            "title": "Second block",
            "start_at": "2035-07-11T10:30:00+03:00",
            "end_at": "2035-07-11T11:30:00+03:00",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["status"] == "conflict"
    assert conflict.json()["reason"] == "calendar_conflict"
    assert conflict.json()["event"] is None
    assert conflict.json()["conflict_event_id"] == first.json()["event"]["id"]

    invalid = await client.post(
        "/api/calendar/work-blocks",
        json={
            "task_id": second_task.json()["task"]["id"],
            "title": "Outside work hours",
            "start_at": "2035-07-11T07:00:00+03:00",
            "end_at": "2035-07-11T08:00:00+03:00",
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["status"] == "invalid"
    assert invalid.json()["reason"] == "outside_work_hours"


async def test_legacy_confirm_endpoint_supports_generic_and_work_blocks(client):
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        generic = await CalendarService(session).create_internal_block(
            user,
            title="Generic proposal",
            start_at=datetime.fromisoformat("2035-07-11T12:00:00+03:00"),
            end_at=datetime.fromisoformat("2035-07-11T13:00:00+03:00"),
            status=CalendarEventStatus.PROPOSED,
        )
        generic_id = str(generic.id)

    generic_confirmed = await client.post(f"/api/calendar/blocks/{generic_id}/confirm")
    assert generic_confirmed.status_code == 200
    assert set(generic_confirmed.json()) == {"event"}
    assert generic_confirmed.json()["event"]["status"] == "confirmed"

    task = await client.post("/api/tasks", json={"title": "Legacy work block"})
    work_block = await client.post(
        "/api/calendar/work-blocks",
        json={
            "task_id": task.json()["task"]["id"],
            "title": "Legacy work block",
            "start_at": "2035-07-11T14:00:00+03:00",
            "end_at": "2035-07-11T15:00:00+03:00",
        },
    )
    legacy_confirmed = await client.post(
        f"/api/calendar/blocks/{work_block.json()['event']['id']}/confirm"
    )
    assert legacy_confirmed.status_code == 200
    assert set(legacy_confirmed.json()) == {"event"}
    assert legacy_confirmed.json()["event"]["kind"] == "work_block"
    assert legacy_confirmed.json()["event"]["status"] == "confirmed"


async def test_pending_suggestions_can_be_listed_and_dismissed(client):
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        suggestion = await AssistantSuggestionService(session).create(
            user,
            kind="micro_slot",
            title="Окно 16:10–16:25",
            description="2 задачи готовы",
            payload={
                "slot": {"start_at": utc_now().isoformat(), "end_at": utc_now().isoformat()},
                "tasks": [{"title": "Проверить почту", "estimated_minutes": 5}],
            },
            context_hash="ctx-1",
        )

    response = await client.get("/api/assistant/suggestions")
    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == str(suggestion.id)
    assert response.json()["items"][0]["status"] == "pending"

    dismissed = await client.post(f"/api/assistant/suggestions/{suggestion.id}/dismiss")
    assert dismissed.status_code == 200
    assert dismissed.json()["suggestion"]["status"] == "dismissed"


async def test_accepting_task_estimate_suggestion_updates_task_estimate(client):
    created = await client.post("/api/tasks", json={"title": "Compare Mira design", "project": "Lumi"})
    task_id = created.json()["task"]["id"]
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        suggestion = await AssistantSuggestionService(session).create(
            user,
            kind="task_estimate",
            title="Estimate Compare Mira design",
            description="Fits a focus block today",
            payload={"task_id": task_id, "estimated_minutes": 45, "reason": "Fits a focus block today"},
            affected_task_ids=[task_id],
        )

    accepted = await client.post(f"/api/assistant/suggestions/{suggestion.id}/accept")

    assert accepted.status_code == 200
    assert accepted.json()["suggestion"]["status"] == AssistantSuggestionStatus.ACCEPTED.value
    tasks = (await client.get("/api/tasks", params={"filter": "all"})).json()["items"]
    task = next(item for item in tasks if item["id"] == task_id)
    assert task["estimated_minutes"] == 45
    assert task["estimate_source"] == "assistant"


async def test_accepting_due_date_suggestion_updates_task_due_date(client):
    created = await client.post("/api/tasks", json={"title": "Prepare roadmap", "project": "Lumi"})
    task_id = created.json()["task"]["id"]
    due_at = (utc_now() + timedelta(days=3)).replace(microsecond=0)
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        suggestion = await AssistantSuggestionService(session).create(
            user,
            kind="task_due_date",
            title="Plan date",
            payload={"task_id": task_id, "due_at": due_at.isoformat(), "reason": "Likely this week"},
            affected_task_ids=[task_id],
        )

    accepted = await client.post(f"/api/assistant/suggestions/{suggestion.id}/accept")

    assert accepted.status_code == 200
    tasks = (await client.get("/api/tasks", params={"filter": "all"})).json()["items"]
    task = next(item for item in tasks if item["id"] == task_id)
    assert task["due_at"] == due_at.isoformat()


async def test_accepting_project_suggestion_updates_task_project(client):
    due_at = (utc_now() + timedelta(days=1)).isoformat()
    created = await client.post("/api/tasks", json={"title": "Sort me", "due_at": due_at})
    task_id = created.json()["task"]["id"]
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        suggestion = await AssistantSuggestionService(session).create(
            user,
            kind="task_project",
            title="Sort into Backlog",
            payload={"task_id": task_id, "project": "Backlog", "reason": "Looks like a backlog item"},
            affected_task_ids=[task_id],
        )

    accepted = await client.post(f"/api/assistant/suggestions/{suggestion.id}/accept")

    assert accepted.status_code == 200
    task = next(item for item in (await client.get("/api/tasks", params={"filter": "all"})).json()["items"] if item["id"] == task_id)
    assert task["project"] == "Backlog"
    assert task["project_id"] is not None


async def test_legacy_review_filter_is_only_an_inbox_alias(client):
    created = await client.post("/api/tasks", json={"title": "Inbox capture"})
    task_id = created.json()["task"]["id"]

    patched = await client.patch(f"/api/tasks/{task_id}", json={"review_skips": {"project": True}})

    assert patched.status_code == 200
    assert patched.json()["task"]["review_skips"] == {"project": True}
    await client.post(
        "/api/tasks",
        json={
            "title": "Planned without optional fields",
            "planned_for": (utc_now() + timedelta(days=1)).isoformat(),
        },
    )
    response = await client.get("/api/tasks", params={"filter": "review"})
    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["Inbox capture"]


async def test_today_filters_past_proposed_blocks_and_does_not_duplicate_inline_suggestions(client, monkeypatch):
    now = datetime(2026, 6, 10, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(today_module, "utc_now", lambda: now)
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        session.add_all([
            CalendarEvent(
                user_id=user.id,
                title="Past proposal",
                start_at=now - timedelta(hours=3),
                end_at=now - timedelta(hours=2),
                timezone=user.timezone,
                all_day=False,
                busy=True,
                status=CalendarEventStatus.PROPOSED,
                source=CalendarSource.INTERNAL,
                created_by="agent",
            ),
            CalendarEvent(
                user_id=user.id,
                title="Future proposal",
                start_at=now + timedelta(hours=1),
                end_at=now + timedelta(hours=2),
                timezone=user.timezone,
                all_day=False,
                busy=True,
                status=CalendarEventStatus.PROPOSED,
                source=CalendarSource.INTERNAL,
                created_by="agent",
            ),
        ])

    response = await client.get("/api/today")

    assert response.status_code == 200
    payload = response.json()
    titles = [item["title"] for item in payload["timeline"]]
    assert "Past proposal" not in titles
    assert "Future proposal" in titles
    assert all(item["kind"] != "focus_block" for item in payload["suggestions"])


async def test_today_includes_pending_micro_slot_suggestions_separately(client, monkeypatch):
    now = datetime(2026, 6, 10, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(today_module, "utc_now", lambda: now)
    start_at = now + timedelta(minutes=30)
    end_at = start_at + timedelta(minutes=25)
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        await AssistantSuggestionService(session).create(
            user,
            kind="micro_slot",
            title="25 min free",
            description="2 quick wins ready",
            start_at=start_at,
            end_at=end_at,
            payload={
                "slot": {"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
                "tasks": [{"id": "task-1", "title": "Check mail", "estimated_minutes": 5}],
                "reason": "Fits this window.",
                "source": "llm",
            },
            context_hash="slot-test",
        )

    response = await client.get("/api/today")

    assert response.status_code == 200
    payload = response.json()
    assert payload["slot_suggestions"][0]["title"] == "25 min free"
    assert payload["slot_suggestions"][0]["tasks"][0]["title"] == "Check mail"
    assert all(item["kind"] != "micro_slot" for item in payload["suggestions"])
