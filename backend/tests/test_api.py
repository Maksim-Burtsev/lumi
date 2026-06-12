import httpx
import pytest

from lumi.api.deps import get_current_user
from lumi.db.session import session_scope
from lumi.main import app
from lumi.services.users import UserService

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


@pytest.fixture
async def anon_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(anon_client):
    response = await anon_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "Lumi"


async def test_api_requires_auth(anon_client):
    response = await anon_client.get("/api/today")
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


async def test_me(client):
    response = await client.get("/api/me")
    assert response.status_code == 200
    assert response.json()["user"]["telegram_user_id"] == TEST_TELEGRAM_ID


async def test_today_shape(client):
    response = await client.get("/api/today")
    assert response.status_code == 200
    body = response.json()
    for key in ("date", "greeting", "summary", "timeline", "needs_attention",
                "suggestions", "recent_runs"):
        assert key in body
    assert body["summary"]["tasks_active"] == 0


async def test_tasks_crud(client):
    create = await client.post("/api/tasks", json={"title": "Тест из API", "priority": "high"})
    assert create.status_code == 201
    task = create.json()["task"]
    assert task["title"] == "Тест из API"

    listing = await client.get("/api/tasks")
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1

    complete = await client.post(f"/api/tasks/{task['id']}/complete")
    assert complete.status_code == 200
    assert complete.json()["task"]["status"] == "done"


async def test_memories_and_automations_endpoints(client):
    memories = await client.get("/api/memories")
    assert memories.status_code == 200
    assert memories.json() == {"items": []}

    create = await client.post("/api/automations", json={
        "type": "news_digest", "title": "Утро", "cron_expression": "30 8 * * 1-5",
        "enabled": False,
    })
    assert create.status_code == 201
    listing = await client.get("/api/automations")
    assert len(listing.json()["items"]) == 1

    bad = await client.post("/api/automations", json={
        "type": "news_digest", "title": "x", "cron_expression": "мусор",
    })
    assert bad.status_code == 422


async def test_calendar_events_crud(client):
    create = await client.post("/api/calendar/events", json={
        "title": "Фокус", "start_at": "2026-06-11T10:00:00+03:00",
        "end_at": "2026-06-11T11:30:00+03:00",
    })
    assert create.status_code == 201
    listing = await client.get(
        "/api/calendar/events",
        params={"start": "2026-06-11T00:00:00+03:00", "end": "2026-06-12T00:00:00+03:00"},
    )
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["source"] == "internal"


async def test_inbox_disconnected(client):
    summary = await client.get("/api/inbox/summary")
    assert summary.status_code == 200
    assert summary.json()["connected"] is False

    run = await client.post("/api/inbox/triage/run")
    assert run.status_code == 409
    assert run.json()["error"] == "google_not_connected"
