from __future__ import annotations

from datetime import datetime

import httpx
import pytest
from sqlalchemy import select

from lumi.api.deps import get_current_user
from lumi.db.models import CalendarEvent, CalendarSource, ToolCall
from lumi.db.session import session_scope
from lumi.llm.gateway import LLMGateway
from lumi.main import app
from lumi.services.calendar import (
    PRIVATE_NOTE_SUMMARY_MAX_CHARS,
    PRIVATE_NOTE_SUMMARY_THRESHOLD_CHARS,
    CalendarService,
    clean_private_note_summary,
)
from lumi.services.users import UserService
from lumi.utils.time import local_to_utc
from lumi.worker.jobs import summarize_calendar_private_note

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


def _long_note() -> str:
    return (
        "Discuss launch risk, partner alignment, integration fallback, owner for rollout notes, "
        "and the exact decision that must be made before the Friday checkpoint. "
    ) * 8


async def test_calendar_service_sets_short_private_note_without_summary(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    event = await CalendarService(db_session).create_internal_block(
        user,
        title="Product sync",
        start_at=local_to_utc(datetime(2026, 6, 24, 10, 0), user.timezone),
        end_at=local_to_utc(datetime(2026, 6, 24, 11, 0), user.timezone),
        created_by="test",
    )

    updated = await CalendarService(db_session).set_private_note(
        user,
        event,
        "Ask about rollout owner.",
    )

    assert updated.metadata_["private_note"] == "Ask about rollout owner."
    assert updated.metadata_["private_note_summary_status"] == "not_needed"
    assert "private_note_summary" not in updated.metadata_
    assert "private_note_hash" in updated.metadata_


async def test_calendar_service_long_note_marks_summary_pending_then_worker_writes_summary(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    calendar = CalendarService(db_session)
    event = await calendar.create_internal_block(
        user,
        title="Architecture review",
        start_at=local_to_utc(datetime(2026, 6, 24, 12, 0), user.timezone),
        end_at=local_to_utc(datetime(2026, 6, 24, 13, 0), user.timezone),
        created_by="test",
    )
    note = _long_note()
    assert len(" ".join(note.split())) >= PRIVATE_NOTE_SUMMARY_THRESHOLD_CHARS

    updated = await calendar.set_private_note(user, event, note)
    note_hash = updated.metadata_["private_note_hash"]

    assert updated.metadata_["private_note_summary_status"] == "pending"
    assert "private_note_summary" not in updated.metadata_
    await db_session.commit()

    result = await summarize_calendar_private_note(
        {},
        str(user.id),
        event_id=str(event.id),
        private_note_hash=note_hash,
        notify=False,
    )

    assert result.startswith("summarized")
    await db_session.refresh(event)
    assert event.metadata_["private_note_summary_status"] == "ready"
    assert event.metadata_["private_note_summary"]
    assert len(event.metadata_["private_note_summary"]) <= 160


async def test_calendar_service_duplicate_summary_write_does_not_overwrite_ready_summary(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    calendar = CalendarService(db_session)
    event = await calendar.create_internal_block(
        user,
        title="Launch notes",
        start_at=local_to_utc(datetime(2026, 6, 24, 13, 0), user.timezone),
        end_at=local_to_utc(datetime(2026, 6, 24, 14, 0), user.timezone),
        created_by="test",
    )
    updated = await calendar.set_private_note(user, event, _long_note())
    note_hash = updated.metadata_["private_note_hash"]

    await calendar.write_private_note_summary(
        user,
        event,
        note_hash=note_hash,
        summary="Keep this good summary.",
    )
    await calendar.write_private_note_summary(
        user,
        event,
        note_hash=note_hash,
        summary="Late duplicate should not win.",
    )

    assert event.metadata_["private_note_summary_status"] == "ready"
    assert event.metadata_["private_note_summary"] == "Keep this good summary."


async def test_calendar_service_failed_summary_does_not_overwrite_ready_summary(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    calendar = CalendarService(db_session)
    event = await calendar.create_internal_block(
        user,
        title="Launch notes",
        start_at=local_to_utc(datetime(2026, 6, 24, 13, 0), user.timezone),
        end_at=local_to_utc(datetime(2026, 6, 24, 14, 0), user.timezone),
        created_by="test",
    )
    updated = await calendar.set_private_note(user, event, _long_note())
    note_hash = updated.metadata_["private_note_hash"]
    await calendar.write_private_note_summary(
        user,
        event,
        note_hash=note_hash,
        summary="Keep this good summary.",
    )

    await calendar.mark_private_note_summary_failed(
        user,
        event,
        note_hash=note_hash,
        error="late duplicate failed",
    )

    assert event.metadata_["private_note_summary_status"] == "ready"
    assert event.metadata_["private_note_summary"] == "Keep this good summary."


async def test_calendar_service_summary_truncates_on_word_boundary(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    calendar = CalendarService(db_session)
    event = await calendar.create_internal_block(
        user,
        title="Summary shape",
        start_at=local_to_utc(datetime(2026, 6, 24, 15, 0), user.timezone),
        end_at=local_to_utc(datetime(2026, 6, 24, 16, 0), user.timezone),
        created_by="test",
    )
    updated = await calendar.set_private_note(user, event, _long_note())

    await calendar.write_private_note_summary(
        user,
        event,
        note_hash=updated.metadata_["private_note_hash"],
        summary=("summary word " * 30).strip(),
    )

    summary = event.metadata_["private_note_summary"]
    assert len(summary) <= PRIVATE_NOTE_SUMMARY_MAX_CHARS
    assert summary.endswith("…")
    assert summary[:-1].endswith("word")


def test_private_note_summary_rejects_original_note_prefix():
    note = (
        "Перед созвоном с командой нужно самому проверить три вещи. "
        "Первое: сравнить текущий UX личных заметок на Today и Calendar. "
        "Второе: проверить поведение длинной заметки и AI summary. "
        "Третье: зафиксировать правило для chat dump."
    ) * 4
    bad_model_output = note[:500]

    summary = clean_private_note_summary(note, bad_model_output)

    assert len(summary) <= PRIVATE_NOTE_SUMMARY_MAX_CHARS
    assert summary != bad_model_output[: len(summary)]
    assert "сравнить текущий UX" in summary


async def test_calendar_service_shortening_note_removes_stale_summary(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    calendar = CalendarService(db_session)
    event = await calendar.create_internal_block(
        user,
        title="Retro",
        start_at=local_to_utc(datetime(2026, 6, 24, 14, 0), user.timezone),
        end_at=local_to_utc(datetime(2026, 6, 24, 15, 0), user.timezone),
        created_by="test",
    )
    await calendar.set_private_note(user, event, _long_note())
    event.metadata_ = {
        **event.metadata_,
        "private_note_summary": "Old summary",
        "private_note_summary_status": "ready",
    }

    await calendar.set_private_note(user, event, "Bring invoice number.")

    assert event.metadata_["private_note"] == "Bring invoice number."
    assert event.metadata_["private_note_summary_status"] == "not_needed"
    assert "private_note_summary" not in event.metadata_


async def test_private_note_api_update_and_delete(client, monkeypatch):
    enqueued: list[dict] = []

    async def fake_enqueue(job_name: str, *args, **kwargs):
        enqueued.append({"job_name": job_name, "args": args, "kwargs": kwargs})
        return "job-1"

    monkeypatch.setattr("lumi.api.routes.calendar.enqueue_job", fake_enqueue)

    create = await client.post("/api/calendar/events", json={
        "title": "Фокус",
        "start_at": "2026-06-24T10:00:00+03:00",
        "end_at": "2026-06-24T11:00:00+03:00",
    })
    event_id = create.json()["event"]["id"]

    update = await client.put(
        f"/api/calendar/events/{event_id}/private-note",
        json={"note": _long_note()},
    )

    assert update.status_code == 200
    event = update.json()["event"]
    assert event["private_note"]
    assert event["private_note_summary_status"] == "pending"
    assert enqueued[-1]["job_name"] == "summarize_calendar_private_note"

    delete = await client.delete(f"/api/calendar/events/{event_id}/private-note")

    assert delete.status_code == 200
    assert delete.json()["event"]["private_note"] is None
    assert delete.json()["event"]["private_note_summary"] is None
    assert delete.json()["event"]["private_note_summary_status"] is None


async def test_external_sync_preserves_private_note_metadata(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    calendar = CalendarService(db_session)
    event = await calendar.upsert_external_event(
        user,
        source=CalendarSource.YANDEX,
        external_calendar_id="work",
        external_event_id="standup-1",
        title="External standup",
        start_at=local_to_utc(datetime(2026, 6, 24, 9, 0), user.timezone),
        end_at=local_to_utc(datetime(2026, 6, 24, 9, 30), user.timezone),
        location="Room 1",
    )
    await calendar.set_private_note(user, event, "Ask about backend rollout.")

    refreshed = await calendar.upsert_external_event(
        user,
        source=CalendarSource.YANDEX,
        external_calendar_id="work",
        external_event_id="standup-1",
        title="External standup updated",
        start_at=local_to_utc(datetime(2026, 6, 24, 9, 0), user.timezone),
        end_at=local_to_utc(datetime(2026, 6, 24, 9, 45), user.timezone),
        location="Room 2",
    )

    assert refreshed.title == "External standup updated"
    assert refreshed.metadata_["location"] == "Room 2"
    assert refreshed.metadata_["private_note"] == "Ask about backend rollout."
    assert refreshed.metadata_["private_note_summary_status"] == "not_needed"


async def test_calendar_read_uses_summary_instead_of_full_long_private_note(monkeypatch):
    from lumi.assistant.orchestrator import AssistantOrchestrator

    from .test_orchestrator import AgentPlannerProvider

    long_note = _long_note()
    summary = "Ask about launch risk and rollout owner."
    provider = AgentPlannerProvider({
        "mode": "tool_calls",
        "language": "en",
        "tool_calls": [
            {
                "name": "read_calendar_events",
                "args": {
                    "start_at_local": "2026-06-24T00:00:00",
                    "end_at_local": "2026-06-25T00:00:00",
                    "sync_if_needed": False,
                    "include_details": True,
                },
                "confidence": 0.95,
                "requires_confirmation": False,
            }
        ],
        "should_answer_normally": False,
    })

    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        event = await CalendarService(session).create_internal_block(
            user,
            title="Product sync",
            start_at=local_to_utc(datetime(2026, 6, 24, 10, 0), user.timezone),
            end_at=local_to_utc(datetime(2026, 6, 24, 11, 0), user.timezone),
            created_by="test",
        )
        event.metadata_ = {
            **(event.metadata_ or {}),
            "private_note": long_note,
            "private_note_summary": summary,
            "private_note_summary_status": "ready",
        }
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=71,
            text="Show my schedule today.",
        )

    assert summary in result.reply_text
    assert long_note not in result.reply_text


async def test_agent_can_create_block_with_private_note_without_public_description():
    from lumi.assistant.orchestrator import AssistantOrchestrator

    from .test_orchestrator import AgentPlannerProvider

    provider = AgentPlannerProvider({
        "mode": "tool_calls",
        "language": "en",
        "user_visible_status": "Creating the block...",
        "tool_calls": [
            {
                "name": "create_internal_calendar_block",
                "args": {
                    "title": "Private prep",
                    "private_note": "Bring pricing notes and ask about launch risk.",
                    "start_at_local": "2026-06-24T16:00:00",
                    "end_at_local": "2026-06-24T16:30:00",
                    "confidence": 0.95,
                    "requires_confirmation": False,
                },
                "confidence": 0.95,
                "requires_confirmation": False,
            }
        ],
        "should_answer_normally": False,
    })

    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=72,
            text="Add a block with personal notes.",
        )
        event = (await session.execute(select(CalendarEvent))).scalar_one()
        tool_call = (
            await session.execute(
                select(ToolCall).where(ToolCall.tool_name == "create_internal_calendar_block")
            )
        ).scalar_one()

    assert event.description is None
    assert event.metadata_["private_note"] == "Bring pricing notes and ask about launch risk."
    assert tool_call.tool_name == "create_internal_calendar_block"


async def test_agent_can_update_and_delete_private_note_by_event_id():
    from lumi.assistant.orchestrator import AssistantOrchestrator

    from .test_orchestrator import AgentPlannerProvider

    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        event = await CalendarService(session).create_internal_block(
            user,
            title="Board prep",
            start_at=local_to_utc(datetime(2026, 6, 24, 17, 0), user.timezone),
            end_at=local_to_utc(datetime(2026, 6, 24, 17, 30), user.timezone),
            created_by="test",
        )
        provider = AgentPlannerProvider([
            {
                "mode": "tool_calls",
                "language": "en",
                "tool_calls": [
                    {
                        "name": "update_calendar_private_note",
                        "args": {
                            "event_id": str(event.id),
                            "private_note": "Ask whether finance owns the rollout numbers.",
                            "confidence": 0.95,
                            "requires_confirmation": False,
                        },
                        "confidence": 0.95,
                        "requires_confirmation": False,
                    }
                ],
                "should_answer_normally": False,
            },
            {
                "mode": "tool_calls",
                "language": "en",
                "tool_calls": [
                    {
                        "name": "delete_calendar_private_note",
                        "args": {
                            "event_id": str(event.id),
                            "confidence": 0.95,
                            "requires_confirmation": False,
                        },
                        "confidence": 0.95,
                        "requires_confirmation": False,
                    }
                ],
                "should_answer_normally": False,
            },
        ])
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))

        update_result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=73,
            text="Add a personal note to this event.",
        )
        await session.refresh(event)
        assert "Updated personal note" in update_result.reply_text
        assert event.metadata_["private_note"] == "Ask whether finance owns the rollout numbers."

        delete_result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=74,
            text="Delete the personal note.",
        )
        await session.refresh(event)
        tool_calls = (
            await session.execute(select(ToolCall).order_by(ToolCall.created_at.desc()).limit(2))
        ).scalars().all()

    assert "Deleted personal note" in delete_result.reply_text
    assert "private_note" not in (event.metadata_ or {})
    assert sorted(call.tool_name for call in tool_calls) == [
        "delete_calendar_private_note",
        "update_calendar_private_note",
    ]
