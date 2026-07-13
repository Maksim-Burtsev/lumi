from datetime import datetime, time

import httpx
import pytest
from sqlalchemy import select

from lumi.api.deps import get_current_user
from lumi.api.routes import telegram
from lumi.db.models import ScheduledTask, ScheduledTaskType
from lumi.db.session import session_scope
from lumi.main import app
from lumi.services.calendar import CalendarService
from lumi.services.confirmations import ConfirmationService
from lumi.services.users import UserService
from lumi.utils.time import local_now, local_to_utc

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


async def test_telegram_webhook_passes_update_id_to_dispatcher(anon_client, monkeypatch):
    seen: dict = {}

    class FakeSettings:
        telegram_webhook_enabled = True
        telegram_webhook_secret = "secret"
        telegram_bot_token = "123456789:TEST-TOKEN-for-tests-only"

    class FakeSession:
        async def close(self) -> None:
            seen["closed"] = True

    class FakeBot:
        def __init__(self, token: str) -> None:
            seen["token"] = token
            self.session = FakeSession()

    class FakeDispatcher:
        def include_router(self, router) -> None:
            seen["router"] = router

        async def feed_update(self, bot, update, **kwargs) -> None:
            seen["telegram_update_id"] = kwargs["telegram_update_id"]

    monkeypatch.setattr(telegram, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(telegram, "Bot", FakeBot)
    monkeypatch.setattr(telegram, "Dispatcher", FakeDispatcher)

    response = await anon_client.post(
        "/api/telegram/webhook/secret",
        json={"update_id": 4242},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert seen["telegram_update_id"] == 4242
    assert seen["closed"] is True


async def test_me(client):
    response = await client.get("/api/me")
    assert response.status_code == 200
    assert response.json()["user"]["telegram_user_id"] == TEST_TELEGRAM_ID


async def test_patch_settings_accepts_valid_timezone(client):
    response = await client.patch("/api/settings", json={"timezone": "Asia/Yerevan"})

    assert response.status_code == 200
    assert response.json()["user"]["timezone"] == "Asia/Yerevan"


async def test_patch_settings_rejects_invalid_timezone(client):
    response = await client.patch("/api/settings", json={"timezone": "Mars/Olympus"})

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_timezone"}


async def test_patch_settings_accepts_time_format(client):
    response = await client.patch("/api/settings", json={"time_format": "12h"})

    assert response.status_code == 200
    assert response.json()["user"]["settings"]["time_format"] == "12h"


async def test_patch_settings_accepts_auto_time_format(client):
    response = await client.patch("/api/settings", json={"time_format": "auto"})

    assert response.status_code == 200
    assert response.json()["user"]["settings"]["time_format"] == "auto"


@pytest.mark.parametrize("theme_mode", ["telegram", "light", "dark"])
async def test_patch_settings_accepts_theme_mode(client, theme_mode):
    response = await client.patch("/api/settings", json={"theme_mode": theme_mode})

    assert response.status_code == 200
    assert response.json()["user"]["settings"]["theme_mode"] == theme_mode


async def test_patch_settings_rejects_invalid_theme_mode(client):
    response = await client.patch("/api/settings", json={"theme_mode": "system"})

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_theme_mode"}


async def test_patch_settings_rejects_invalid_theme_mode_in_settings_payload(client):
    response = await client.patch("/api/settings", json={"settings": {"theme_mode": "system"}})

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_theme_mode"}


async def test_patch_settings_rejects_invalid_time_format(client):
    response = await client.patch("/api/settings", json={"time_format": "ampm"})

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_time_format"}


async def test_patch_settings_rejects_empty_time_format(client):
    response = await client.patch("/api/settings", json={"time_format": ""})

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_time_format"}


async def test_patch_settings_rejects_invalid_time_format_in_settings_payload(client):
    response = await client.patch("/api/settings", json={"settings": {"time_format": "ampm"}})

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_time_format"}


async def test_timezones_endpoint_returns_full_selectable_list(client):
    response = await client.get("/api/timezones")

    assert response.status_code == 200
    items = response.json()["items"]
    ids = [item["id"] for item in items]
    assert len(ids) > 300
    assert ids == sorted(ids)
    assert "UTC" in ids
    assert "Asia/Yerevan" in ids
    assert "Pacific/Chatham" in ids
    assert "America/St_Johns" in ids
    assert "Asia/Kathmandu" in ids
    assert not any(tz.startswith(("posix/", "right/")) for tz in ids)
    assert not any(tz.startswith(("Etc/", "SystemV/")) for tz in ids)
    assert not any("/" not in tz and tz != "UTC" for tz in ids)
    assert "W-SU" not in ids
    assert "WET" not in ids
    assert "Zulu" not in ids


async def test_today_shape(client):
    response = await client.get("/api/today")
    assert response.status_code == 200
    body = response.json()
    for key in ("date", "greeting", "summary", "timeline", "needs_attention",
                "suggestions", "recent_runs"):
        assert key in body
    assert body["summary"]["tasks_active"] == 0
    assert "emails_need_reply" not in body["summary"]


async def test_today_timeline_includes_personal_note_fields(client, db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    calendar = CalendarService(db_session)
    today = local_now(user.timezone).date()
    event = await calendar.create_internal_block(
        user,
        title="Board prep",
        start_at=local_to_utc(datetime.combine(today, time(10, 0)), user.timezone),
        end_at=local_to_utc(datetime.combine(today, time(10, 30)), user.timezone),
        created_by="test",
    )
    await calendar.set_private_note(user, event, "Ask about launch risk.")
    await db_session.commit()

    response = await client.get("/api/today")

    assert response.status_code == 200
    item = next(item for item in response.json()["timeline"] if item["id"] == str(event.id))
    assert item["private_note"] == "Ask about launch risk."
    assert item["private_note_summary"] is None
    assert item["private_note_summary_status"] == "not_needed"
    assert item["private_note_updated_at"] is not None
    assert item["private_note_summary_updated_at"] is None


async def test_today_hides_auto_memory_confirmations(client, db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    service = ConfirmationService(db_session)
    await service.create(
        user,
        action_type="store_memory",
        action_payload={"kind": "fact", "text": "Скрытая память", "importance": 3, "confidence": 0.9},
        prompt="Запомнить скрытый факт?",
    )
    task_confirmation = await service.create(
        user,
        action_type="create_task",
        action_payload={"title": "Видимая задача", "confidence": 0.8, "requires_confirmation": True},
        prompt="Создать видимую задачу?",
    )
    await db_session.commit()

    response = await client.get("/api/today")
    assert response.status_code == 200
    items = response.json()["needs_attention"]
    assert all(item.get("action_type") != "store_memory" for item in items)
    assert any(item.get("ref_id") == str(task_confirmation.id) for item in items)


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


async def test_memories_endpoint(client):
    memories = await client.get("/api/memories")
    assert memories.status_code == 200
    assert memories.json() == {"items": []}


async def test_confirmations_accept_and_reject(client, db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID, language_code="ru")
    service = ConfirmationService(db_session)
    accept_item = await service.create(
        user,
        action_type="store_memory",
        action_payload={
            "kind": "fact",
            "text": "Пользователь тестирует confirmation API",
            "importance": 3,
            "confidence": 0.9,
            "requires_confirmation": True,
        },
        prompt="Запомнить тестовый факт?",
    )
    reject_item = await service.create(
        user,
        action_type="create_task",
        action_payload={
            "title": "Тестовая задача из confirmation",
            "confidence": 0.8,
            "requires_confirmation": True,
        },
        prompt="Создать тестовую задачу?",
    )
    await db_session.commit()

    accepted = await client.post(f"/api/confirmations/{accept_item.id}/accept")
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["executed"] is True
    assert body["confirmation"]["status"] == "accepted"
    assert body["confirmation"]["risk_class"] == "write_internal_memory"
    assert body["result_text"] == "Remembered."

    rejected = await client.post(f"/api/confirmations/{reject_item.id}/reject")
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["executed"] is False
    assert body["confirmation"]["status"] == "rejected"
    assert body["result_text"] == "Ok, I won't do it."

    again = await client.post(f"/api/confirmations/{reject_item.id}/reject")
    assert again.status_code == 409


async def test_legacy_automation_confirmation_cannot_execute(client, db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID, language_code="en")
    legacy = await ConfirmationService(db_session).create(
        user,
        action_type="create_automation",
        action_payload={
            "type": "custom_prompt",
            "title": "Legacy research",
            "cron_expression": "0 9 * * *",
        },
        prompt="Enable legacy automation?",
    )
    await db_session.commit()

    response = await client.post(f"/api/confirmations/{legacy.id}/accept")

    assert response.status_code == 200
    assert response.json()["executed"] is False
    assert "no longer available" in response.json()["result_text"]
    async with session_scope() as session:
        assert list((await session.execute(select(ScheduledTask))).scalars()) == []


async def test_calendar_events_crud(client):
    create = await client.post("/api/calendar/events", json={
        "title": "Фокус", "start_at": "2026-06-11T10:00:00+03:00",
        "end_at": "2026-06-11T11:30:00+03:00",
        "description": "Контекст https://example.com/spec",
        "location": "Дом",
        "links": ["https://example.com/spec"],
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
    assert items[0]["location"] == "Дом"
    assert items[0]["links"] == ["https://example.com/spec"]


@pytest.mark.parametrize(
    "method,path",
    (
        ("GET", "/api/inbox/summary"),
        ("POST", "/api/inbox/triage/run"),
        ("GET", "/api/news/topics"),
        ("POST", "/api/news/digest/run"),
        ("GET", "/api/automations"),
        ("POST", "/api/automations"),
    ),
)
async def test_removed_product_routes_return_not_found(client, method, path):
    response = await client.request(method, path, json={} if method == "POST" else None)

    assert response.status_code == 404


async def test_google_oauth_callback_is_single_use_and_starts_calendar_sync(
    client,
    db_session,
    monkeypatch,
):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    await db_session.commit()
    exchanged: list[str] = []
    started: list[tuple[str, bool]] = []

    class FakeRedis:
        def __init__(self) -> None:
            self.value: str | None = str(user.id)

        async def get(self, key: str):
            return self.value

        async def delete(self, key: str) -> None:
            self.value = None

    redis = FakeRedis()

    async def fake_exchange_code(code: str) -> None:
        exchanged.append(code)

    async def fake_start_background_run(session, user_arg, run_type, **kwargs):
        started.append((run_type, kwargs["notify"]))
        return {"run_id": "calendar-run", "status": "queued"}

    monkeypatch.setattr("lumi.worker.queue.get_queue", lambda: _async_value(redis))
    monkeypatch.setattr("lumi.connectors.google.auth.exchange_code", fake_exchange_code)
    monkeypatch.setattr("lumi.api.run_helper.start_background_run", fake_start_background_run)

    response = await client.get(
        "/api/connectors/google/callback",
        params={"code": "oauth-code", "state": "single-use-state"},
    )

    assert response.status_code == 200
    assert "Календарь доступен" in response.text
    assert "Почта" not in response.text
    assert exchanged == ["oauth-code"]
    assert started == [("calendar_sync", False)]

    async with session_scope() as session:
        scheduled = list((await session.execute(select(ScheduledTask))).scalars())
        assert len(scheduled) == 1
        assert scheduled[0].type == ScheduledTaskType.CALENDAR_SYNC
        assert scheduled[0].config["system"] is True

    stale = await client.get(
        "/api/connectors/google/callback",
        params={"code": "second-code", "state": "single-use-state"},
    )
    assert "Ссылка устарела" in stale.text
    assert exchanged == ["oauth-code"]


async def _async_value(value):
    return value
