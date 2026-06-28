import httpx
import pytest
from sqlalchemy import select

from lumi.db.models import AgentRunType, UiEvent
from lumi.db.session import session_scope
from lumi.main import app
from lumi.services.realtime import RealtimeEventService
from lumi.services.runs import RunService
from lumi.services.tasks import TaskService
from lumi.services.users import UserService

from .conftest import TEST_TELEGRAM_ID


@pytest.fixture
async def user():
    async with session_scope() as session:
        service = UserService(session)
        user = await service.ensure_user(TEST_TELEGRAM_ID, first_name="Тест", username="tester")
        await service.ensure_main_conversation(user)
    return user


async def test_ui_event_publishes_only_after_commit(user, monkeypatch):
    published = []

    async def fake_publish(events):
        published.extend(events)

    monkeypatch.setattr("lumi.services.realtime.publish_realtime_events", fake_publish)

    async with session_scope() as session:
        await RealtimeEventService(session).emit(
            user_id=user.id,
            topics=["tasks", "today"],
            event_type="task.created",
            payload={"task_id": "task-1"},
        )
        assert published == []

    assert len(published) == 1
    assert published[0]["topics"] == ["tasks", "today"]
    assert published[0]["event_type"] == "task.created"

    async with session_scope() as session:
        rows = list((await session.execute(select(UiEvent))).scalars())
    assert len(rows) == 1
    assert rows[0].topics == ["tasks", "today"]


async def test_ui_event_rollback_does_not_publish_or_persist(user, monkeypatch):
    published = []

    async def fake_publish(events):
        published.extend(events)

    monkeypatch.setattr("lumi.services.realtime.publish_realtime_events", fake_publish)

    with pytest.raises(RuntimeError):
        async with session_scope() as session:
            await RealtimeEventService(session).emit(
                user_id=user.id,
                topics=["tasks"],
                event_type="task.created",
                payload={"task_id": "task-1"},
            )
            raise RuntimeError("force rollback")

    assert published == []
    async with session_scope() as session:
        rows = list((await session.execute(select(UiEvent))).scalars())
    assert rows == []


async def test_list_after_returns_only_requested_user_events(user):
    async with session_scope() as session:
        other_user = await UserService(session).ensure_user(888001, first_name="Other")

    async with session_scope() as session:
        first = await RealtimeEventService(session).emit(
            user_id=user.id,
            topics=["tasks"],
            event_type="task.created",
            payload={"task_id": "first"},
        )
        await RealtimeEventService(session).emit(
            user_id=other_user.id,
            topics=["tasks"],
            event_type="task.created",
            payload={"task_id": "other"},
        )
        second = await RealtimeEventService(session).emit(
            user_id=user.id,
            topics=["calendar"],
            event_type="calendar.updated",
            payload={"event_id": "second"},
        )

    async with session_scope() as session:
        events = await RealtimeEventService(session).list_after(user.id, after=first.id)

    assert [event.id for event in events] == [second.id]


async def test_realtime_endpoint_requires_auth():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/realtime")

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


async def test_task_and_run_services_emit_ui_topics(user, monkeypatch):
    published = []

    async def fake_publish(events):
        published.extend(events)

    monkeypatch.setattr("lumi.services.realtime.publish_realtime_events", fake_publish)

    async with session_scope() as session:
        await TaskService(session).create_task(user, title="Realtime task")
        runs = RunService(session)
        run = await runs.create(user_id=user.id, type_=AgentRunType.CHAT, trigger="test")
        await runs.mark_completed(run, "ok")

    events_by_type = {event["event_type"]: event for event in published}
    assert "task.created" in events_by_type
    assert "run.created" in events_by_type
    assert "run.completed" in events_by_type
    assert "tasks" in events_by_type["task.created"]["topics"]
    assert "runs" in events_by_type["run.created"]["topics"]
