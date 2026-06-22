from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from lumi.assistant.orchestrator import AssistantResult
from lumi.db.models import AssistantTurn, TelegramUpdate
from lumi.db.session import session_scope
from lumi.services.turns import TelegramIntakeService, TurnService
from lumi.utils.time import utc_now
from lumi.worker import jobs

from .conftest import TEST_TELEGRAM_ID

BASE_NOW = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)


async def test_send_turn_reply_uses_html_message_by_default_for_calendar_html(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class FakeBot:
        def __init__(self, token: str) -> None:
            self.token = token
            self.session = SimpleNamespace(close=self._close)

        async def _close(self) -> None:
            calls.append(("close", {}))

        async def send_message(self, **kwargs):
            calls.append(("send_message", kwargs))
            return SimpleNamespace(message_id=11)

    async def fake_telegram_api_post(token: str, method: str, payload: dict):
        raise AssertionError(f"unexpected raw Telegram API call: {method}")

    monkeypatch.setattr("aiogram.Bot", FakeBot)
    monkeypatch.setattr(jobs, "_telegram_api_post", fake_telegram_api_post)
    monkeypatch.setattr(
        jobs,
        "get_settings",
        lambda: SimpleNamespace(telegram_bot_token="123:test"),
    )

    delivered = await jobs.send_turn_reply(
        user=SimpleNamespace(telegram_chat_id=777, telegram_user_id=777),
        turn=SimpleNamespace(telegram_chat_id=777, status_message_id=None),
        reply_text="Встречи в календаре:\n13:00–13:15 — Standup — https://meet.example/a",
        reply_rich_html='<b>📅 Встречи</b>\n<b>13:00–13:15</b> Standup <a href="https://meet.example/a">↗ открыть звонок</a>',
        buttons=[],
    )

    assert delivered is True
    assert [name for name, _ in calls] == ["send_message", "close"]
    message = calls[0][1]
    assert message["parse_mode"] == "HTML"
    assert message["text"].startswith("<b>📅 Встречи</b>")
    assert "↗ открыть звонок" in message["text"]
    assert message["link_preview_options"].is_disabled is True


async def test_send_turn_reply_uses_bot_api_rich_message_when_enabled(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class FakeBot:
        def __init__(self, token: str) -> None:
            self.token = token
            self.session = SimpleNamespace(close=self._close)

        async def _close(self) -> None:
            calls.append(("close", {}))

        async def send_message(self, **kwargs):
            calls.append(("send_message", kwargs))
            return SimpleNamespace(message_id=11)

    async def fake_telegram_api_post(token: str, method: str, payload: dict):
        calls.append((method, payload | {"token": token}))
        return {"ok": True, "result": {"message_id": 10}}

    monkeypatch.setattr("aiogram.Bot", FakeBot)
    monkeypatch.setattr(jobs, "_telegram_api_post", fake_telegram_api_post)
    monkeypatch.setattr(
        jobs,
        "get_settings",
        lambda: SimpleNamespace(telegram_bot_token="123:test", telegram_use_rich_messages=True),
    )

    delivered = await jobs.send_turn_reply(
        user=SimpleNamespace(telegram_chat_id=777, telegram_user_id=777),
        turn=SimpleNamespace(telegram_chat_id=777, status_message_id=None),
        reply_text="Встречи в календаре:\n13:00–13:15 — Standup — https://meet.example/a",
        reply_rich_html='<b>📅 Встречи</b><br>13:00–13:15 Standup <a href="https://meet.example/a">↗ открыть звонок</a>',
        buttons=[],
    )

    assert delivered is True
    assert [name for name, _ in calls] == ["sendRichMessage", "close"]
    rich_message = calls[0][1]["rich_message"]
    assert calls[0][1]["token"] == "123:test"
    assert rich_message["html"].startswith("<b>📅 Встречи</b>")
    assert rich_message["skip_entity_detection"] is True
    assert "https://meet.example/a" in rich_message["html"]


async def test_send_turn_reply_falls_back_to_html_when_rich_send_fails(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class FakeBot:
        def __init__(self, token: str) -> None:
            self.token = token
            self.session = SimpleNamespace(close=self._close)

        async def _close(self) -> None:
            calls.append(("close", {}))

        async def send_message(self, **kwargs):
            calls.append(("send_message", kwargs))
            return SimpleNamespace(message_id=12)

    async def fake_telegram_api_post(token: str, method: str, payload: dict):
        calls.append((method, payload | {"token": token}))
        if method == "sendRichMessage":
            raise RuntimeError("rich unsupported")
        return {"ok": True, "result": True}

    monkeypatch.setattr("aiogram.Bot", FakeBot)
    monkeypatch.setattr(jobs, "_telegram_api_post", fake_telegram_api_post)
    monkeypatch.setattr(
        jobs,
        "get_settings",
        lambda: SimpleNamespace(telegram_bot_token="123:test", telegram_use_rich_messages=True),
    )

    delivered = await jobs.send_turn_reply(
        user=SimpleNamespace(telegram_chat_id=777, telegram_user_id=777),
        turn=SimpleNamespace(telegram_chat_id=777, status_message_id=None),
        reply_text="Встречи в календаре:\n13:00–13:15 — Standup — https://meet.example/a",
        reply_rich_html='<b>📅 Встречи</b>',
        buttons=[],
    )

    assert delivered is True
    assert [name for name, _ in calls] == ["sendRichMessage", "send_message", "close"]
    fallback = calls[1][1]
    assert fallback["text"] == '<b>📅 Встречи</b>'
    assert fallback["parse_mode"] == "HTML"
    assert fallback["link_preview_options"].is_disabled is True


async def test_intake_debounces_fast_messages_into_one_turn():
    async with session_scope() as session:
        intake = TelegramIntakeService(session, now=lambda: BASE_NOW)

        first = await intake.ingest_chat_message(
            update_id=1001,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=501,
            text="первое",
        )
        second = await intake.ingest_chat_message(
            update_id=1002,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=502,
            text="второе",
        )

        assert first.duplicate_update is False
        assert second.duplicate_update is False
        assert first.turn.id == second.turn.id
        assert second.should_enqueue is True
        assert second.enqueue_at == BASE_NOW + timedelta(milliseconds=1200)

        turn = await session.get(AssistantTurn, first.turn.id)
        assert turn is not None
        assert turn.sequence_no == 1
        assert turn.status == "collecting"
        assert turn.input_text == "первое\n\nвторое"
        assert turn.source_update_ids == [1001, 1002]
        assert turn.source_message_ids == [501, 502]


async def test_duplicate_update_does_not_create_second_turn():
    async with session_scope() as session:
        intake = TelegramIntakeService(session, now=lambda: BASE_NOW)

        first = await intake.ingest_chat_message(
            update_id=1101,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=601,
            text="один раз",
        )
        duplicate = await intake.ingest_chat_message(
            update_id=1101,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=601,
            text="один раз",
        )

        assert first.duplicate_update is False
        assert duplicate.duplicate_update is True
        assert duplicate.should_enqueue is False

        turns = (await session.execute(select(AssistantTurn))).scalars().all()
        updates = (await session.execute(select(TelegramUpdate))).scalars().all()
        assert len(turns) == 1
        assert len(updates) == 1


async def test_per_user_lock_prevents_two_running_turns():
    async with session_scope() as session:
        intake = TelegramIntakeService(session, now=lambda: BASE_NOW)
        first = await intake.ingest_chat_message(
            update_id=1201,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=701,
            text="первый turn",
        )

        later = BASE_NOW + timedelta(seconds=3)
        intake_later = TelegramIntakeService(session, now=lambda: later)
        second = await intake_later.ingest_chat_message(
            update_id=1202,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=702,
            text="второй turn",
        )

        after_second_deadline = later + timedelta(seconds=2)
        turns = TurnService(session, now=lambda: after_second_deadline)
        acquired_first = await turns.acquire_turn(first.turn.id, lock_seconds=300)
        acquired_second = await turns.acquire_turn(second.turn.id, lock_seconds=300)

        assert acquired_first.status == "acquired"
        assert acquired_first.turn is not None
        assert acquired_first.turn.status == "running"
        assert acquired_second.status == "locked"
        assert acquired_second.turn is None


async def test_complete_turn_returns_next_fifo_turn():
    async with session_scope() as session:
        intake = TelegramIntakeService(session, now=lambda: BASE_NOW)
        first = await intake.ingest_chat_message(
            update_id=1301,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=801,
            text="первый",
        )
        later = BASE_NOW + timedelta(seconds=3)
        second = await TelegramIntakeService(session, now=lambda: later).ingest_chat_message(
            update_id=1302,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=802,
            text="второй",
        )

        after_second_deadline = later + timedelta(seconds=2)
        turns = TurnService(session, now=lambda: after_second_deadline)
        acquired = await turns.acquire_turn(first.turn.id, lock_seconds=300)
        assert acquired.status == "acquired"

        next_turn = await turns.complete_turn(first.turn.id)

    assert next_turn is not None
    assert next_turn.id == second.turn.id
    assert next_turn.sequence_no == 2


async def test_fail_turn_returns_next_fifo_turn():
    async with session_scope() as session:
        intake = TelegramIntakeService(session, now=lambda: BASE_NOW)
        first = await intake.ingest_chat_message(
            update_id=1321,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=821,
            text="первый",
        )
        later = BASE_NOW + timedelta(seconds=3)
        second = await TelegramIntakeService(session, now=lambda: later).ingest_chat_message(
            update_id=1322,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=822,
            text="второй",
        )

        after_second_deadline = later + timedelta(seconds=2)
        turns = TurnService(session, now=lambda: after_second_deadline)
        acquired = await turns.acquire_turn(first.turn.id, lock_seconds=300)
        assert acquired.status == "acquired"

        next_turn = await turns.fail_turn(first.turn.id, "boom")

    assert next_turn is not None
    assert next_turn.id == second.turn.id
    assert next_turn.sequence_no == 2


async def test_second_message_ingests_while_first_turn_is_running(monkeypatch):
    started = utc_now() - timedelta(seconds=10)
    orchestrator_started = asyncio.Event()
    release_orchestrator = asyncio.Event()

    async with session_scope() as session:
        result = await TelegramIntakeService(session, now=lambda: started).ingest_chat_message(
            update_id=1351,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=851,
            text="долгий turn",
        )
        turn_id = result.turn.id

    class SlowOrchestrator:
        def __init__(self, session) -> None:
            self.session = session

        async def handle_user_message(self, **kwargs):
            orchestrator_started.set()
            await release_orchestrator.wait()
            return AssistantResult(reply_text="готово", buttons=[], needs_compaction=False)

    async def fake_send_turn_reply(*, user, turn, reply_text, buttons):
        return True

    monkeypatch.setattr(jobs, "AssistantOrchestrator", SlowOrchestrator)
    monkeypatch.setattr(jobs, "send_turn_reply", fake_send_turn_reply)

    task = asyncio.create_task(jobs.process_assistant_turn({}, str(turn_id)))
    await asyncio.wait_for(orchestrator_started.wait(), timeout=2)

    async def ingest_second_message():
        async with session_scope() as session:
            return await TelegramIntakeService(session).ingest_chat_message(
                update_id=1352,
                telegram_user_id=TEST_TELEGRAM_ID,
                telegram_chat_id=TEST_TELEGRAM_ID,
                telegram_message_id=852,
                text="следом",
            )

    second = await asyncio.wait_for(ingest_second_message(), timeout=1)
    assert second.turn is not None
    assert second.turn.id != turn_id

    release_orchestrator.set()
    assert await task == "turn completed"


async def test_duplicate_job_for_running_turn_does_not_enqueue_retry(monkeypatch):
    started = utc_now() - timedelta(seconds=10)
    orchestrator_started = asyncio.Event()
    release_orchestrator = asyncio.Event()
    requeued: list[tuple[str, tuple, dict]] = []

    async with session_scope() as session:
        result = await TelegramIntakeService(session, now=lambda: started).ingest_chat_message(
            update_id=1353,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=853,
            text="дубликат job",
        )
        turn_id = result.turn.id

    class SlowOrchestrator:
        def __init__(self, session) -> None:
            self.session = session

        async def handle_user_message(self, **kwargs):
            orchestrator_started.set()
            await release_orchestrator.wait()
            return AssistantResult(reply_text="готово", buttons=[], needs_compaction=False)

    async def fake_send_turn_reply(*, user, turn, reply_text, buttons):
        return True

    async def fake_enqueue(job_name, *args, **kwargs):
        requeued.append((job_name, args, kwargs))
        return "job-id"

    monkeypatch.setattr(jobs, "AssistantOrchestrator", SlowOrchestrator)
    monkeypatch.setattr(jobs, "send_turn_reply", fake_send_turn_reply)
    monkeypatch.setattr(jobs, "enqueue_job", fake_enqueue)

    first_job = asyncio.create_task(jobs.process_assistant_turn({}, str(turn_id)))
    await asyncio.wait_for(orchestrator_started.wait(), timeout=2)

    duplicate_summary = await jobs.process_assistant_turn({}, str(turn_id))

    assert duplicate_summary == "turn already running"
    assert requeued == []

    release_orchestrator.set()
    assert await first_job == "turn completed"


async def test_enqueue_turn_uses_deadline_scoped_job_id(monkeypatch):
    captured: dict = {}
    turn = AssistantTurn(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        sequence_no=1,
        input_text="x",
        telegram_chat_id=TEST_TELEGRAM_ID,
        debounce_deadline_at=BASE_NOW,
    )

    async def fake_enqueue(job_name, *args, **kwargs):
        captured["job_name"] = job_name
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "job-id"

    monkeypatch.setattr(jobs, "enqueue_job", fake_enqueue)

    await jobs._enqueue_turn(turn)

    assert captured["job_name"] == "process_assistant_turn"
    assert captured["args"] == (str(turn.id),)
    assert captured["kwargs"]["_job_id"] == f"assistant-turn:{turn.id}:at:1781517600000"


async def test_short_retry_enqueue_does_not_use_stale_result_job_id(monkeypatch):
    captured: dict = {}
    turn_id = str(uuid.uuid4())

    async def fake_enqueue(job_name, *args, **kwargs):
        captured["job_name"] = job_name
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "job-id"

    monkeypatch.setattr(jobs, "enqueue_job", fake_enqueue)

    await jobs._enqueue_turn_id(turn_id, delay_seconds=3)

    assert captured["job_name"] == "process_assistant_turn"
    assert captured["args"] == (turn_id,)
    assert captured["kwargs"] == {"_defer_by": timedelta(seconds=3)}


async def test_acquire_turn_locks_user_before_turn_row_to_avoid_deadlocks():
    turn_id = uuid.uuid4()
    user_id = uuid.uuid4()
    calls: list[str] = []

    class FakeResult:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class FakeSession:
        async def execute(self, statement):
            text = str(statement)
            calls.append(text)
            if "assistant_turns.user_id" in text and "FOR UPDATE" not in text:
                return FakeResult(user_id)
            if "FROM users" in text:
                return FakeResult(None)
            if "FROM assistant_turns" in text and "FOR UPDATE" in text:
                return FakeResult(
                    AssistantTurn(
                        id=turn_id,
                        user_id=user_id,
                        conversation_id=uuid.uuid4(),
                        sequence_no=1,
                        input_text="x",
                        telegram_chat_id=TEST_TELEGRAM_ID,
                        debounce_deadline_at=BASE_NOW - timedelta(seconds=1),
                    )
                )
            return FakeResult(None)

    service = TurnService(FakeSession(), now=lambda: BASE_NOW)  # type: ignore[arg-type]

    await service.acquire_turn(turn_id, lock_seconds=300)

    locking_calls = [call for call in calls if "FOR UPDATE" in call]
    assert locking_calls
    assert "FROM users" in locking_calls[0]


async def test_debounce_append_keeps_original_status_message():
    async with session_scope() as session:
        intake = TelegramIntakeService(session, now=lambda: BASE_NOW)
        first = await intake.ingest_chat_message(
            update_id=1361,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=861,
            text="первое",
            status_message_id=9001,
        )
        second = await intake.ingest_chat_message(
            update_id=1362,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=862,
            text="второе",
            status_message_id=9002,
        )

        assert first.created_turn is True
        assert second.created_turn is False
        assert second.turn.id == first.turn.id
        assert second.turn.status_message_id == 9001


async def test_process_assistant_turn_runs_orchestrator_and_completes(monkeypatch):
    started = utc_now() - timedelta(seconds=10)
    seen: dict = {}
    sent: list[str] = []
    requeued: list[str] = []

    async with session_scope() as session:
        result = await TelegramIntakeService(session, now=lambda: started).ingest_chat_message(
            update_id=1401,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=901,
            text="ответь",
        )
        turn_id = result.turn.id

    class FakeOrchestrator:
        def __init__(self, session) -> None:
            self.session = session

        async def handle_user_message(self, **kwargs):
            seen.update(kwargs)
            return AssistantResult(reply_text="готово", buttons=[], needs_compaction=False)

    async def fake_send_turn_reply(*, user, turn, reply_text, buttons):
        sent.append(reply_text)
        return True

    async def fake_enqueue(job_name, *args, **kwargs):
        requeued.append(job_name)
        return "job-id"

    monkeypatch.setattr(jobs, "AssistantOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(jobs, "send_turn_reply", fake_send_turn_reply)
    monkeypatch.setattr(jobs, "enqueue_job", fake_enqueue)

    summary = await jobs.process_assistant_turn({}, str(turn_id))

    assert summary == "turn completed"
    assert seen["telegram_message_id"] == 901
    assert seen["text"] == "ответь"
    assert seen["touch_last_seen"] is False
    assert sent == ["готово"]
    assert requeued == []
    async with session_scope() as session:
        turn = await session.get(AssistantTurn, turn_id)
        assert turn.status == "completed"


async def test_process_assistant_turn_edits_progress_status(monkeypatch):
    started = utc_now() - timedelta(seconds=10)
    edits: list[tuple[int, str]] = []

    async with session_scope() as session:
        result = await TelegramIntakeService(session, now=lambda: started).ingest_chat_message(
            update_id=1451,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=911,
            text="add a calendar block",
            status_message_id=9101,
        )
        turn_id = result.turn.id

    class FakeOrchestrator:
        def __init__(self, session) -> None:
            self.session = session

        async def handle_user_message(self, **kwargs):
            await kwargs["on_progress"]("Checking your calendar...")
            return AssistantResult(reply_text="done", buttons=[], needs_compaction=False)

    async def fake_edit_turn_status_message(*, user, turn, status_text):
        edits.append((turn.status_message_id, status_text))
        return True

    async def fake_send_turn_reply(*, user, turn, reply_text, buttons):
        return True

    monkeypatch.setattr(jobs, "AssistantOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(jobs, "edit_turn_status_message", fake_edit_turn_status_message)
    monkeypatch.setattr(jobs, "send_turn_reply", fake_send_turn_reply)

    summary = await jobs.process_assistant_turn({}, str(turn_id))

    assert summary == "turn completed"
    assert edits == [(9101, "Checking your calendar...")]


async def test_delivery_failure_retries_and_does_not_complete(monkeypatch):
    started = utc_now() - timedelta(seconds=10)
    requeued: list[tuple[str, tuple, dict]] = []

    async with session_scope() as session:
        result = await TelegramIntakeService(session, now=lambda: started).ingest_chat_message(
            update_id=1501,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=951,
            text="ответь",
        )
        turn_id = result.turn.id

    class FakeOrchestrator:
        def __init__(self, session) -> None:
            self.session = session

        async def handle_user_message(self, **kwargs):
            return AssistantResult(reply_text="готово", buttons=[], needs_compaction=False)

    async def fake_send_turn_reply(*, user, turn, reply_text, buttons):
        return False

    async def fake_enqueue(job_name, *args, **kwargs):
        requeued.append((job_name, args, kwargs))
        return "retry-job-id"

    monkeypatch.setattr(jobs, "AssistantOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(jobs, "send_turn_reply", fake_send_turn_reply)
    monkeypatch.setattr(jobs, "enqueue_job", fake_enqueue)

    summary = await jobs.process_assistant_turn({}, str(turn_id))

    assert summary == "turn delivery retry scheduled"
    assert requeued[0][0] == "process_assistant_turn"
    assert requeued[0][1] == (str(turn_id),)
    assert requeued[0][2]["_job_id"].startswith(f"assistant-turn:{turn_id}:at:")
    async with session_scope() as session:
        turn = await session.get(AssistantTurn, turn_id)
        assert turn.status == "queued"
        assert turn.retry_count == 1
        assert turn.finished_at is None


async def test_delivery_failure_marks_turn_failed_after_max_retries(monkeypatch):
    started = utc_now() - timedelta(seconds=10)

    async with session_scope() as session:
        result = await TelegramIntakeService(session, now=lambda: started).ingest_chat_message(
            update_id=1502,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=952,
            text="ответь",
        )
        turn_id = result.turn.id
        result.turn.retry_count = 2

    class FakeOrchestrator:
        def __init__(self, session) -> None:
            self.session = session

        async def handle_user_message(self, **kwargs):
            return AssistantResult(reply_text="готово", buttons=[], needs_compaction=False)

    async def fake_send_turn_reply(*, user, turn, reply_text, buttons):
        return False

    monkeypatch.setattr(jobs, "AssistantOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(jobs, "send_turn_reply", fake_send_turn_reply)

    summary = await jobs.process_assistant_turn({}, str(turn_id))

    assert summary == "turn delivery failed"
    async with session_scope() as session:
        turn = await session.get(AssistantTurn, turn_id)
        assert turn.status == "failed"
        assert turn.retry_count == 3
        assert turn.finished_at is not None


async def test_delivery_exhaustion_enqueues_next_turn(monkeypatch):
    started = utc_now() - timedelta(seconds=20)
    requeued: list[tuple[str, tuple, dict]] = []

    async with session_scope() as session:
        first = await TelegramIntakeService(session, now=lambda: started).ingest_chat_message(
            update_id=1511,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=961,
            text="первый",
        )
        second = await TelegramIntakeService(
            session,
            now=lambda: started + timedelta(seconds=3),
        ).ingest_chat_message(
            update_id=1512,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=962,
            text="второй",
        )
        first.turn.retry_count = 2

    class FakeOrchestrator:
        def __init__(self, session) -> None:
            self.session = session

        async def handle_user_message(self, **kwargs):
            return AssistantResult(reply_text="готово", buttons=[], needs_compaction=False)

    async def fake_send_turn_reply(*, user, turn, reply_text, buttons):
        return False

    async def fake_enqueue(job_name, *args, **kwargs):
        requeued.append((job_name, args, kwargs))
        return "job-id"

    monkeypatch.setattr(jobs, "AssistantOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(jobs, "send_turn_reply", fake_send_turn_reply)
    monkeypatch.setattr(jobs, "enqueue_job", fake_enqueue)

    summary = await jobs.process_assistant_turn({}, str(first.turn.id))

    assert summary == "turn delivery failed"
    assert requeued[0][0] == "process_assistant_turn"
    assert requeued[0][1] == (str(second.turn.id),)
    async with session_scope() as session:
        first_turn = await session.get(AssistantTurn, first.turn.id)
        second_turn = await session.get(AssistantTurn, second.turn.id)
        assert first_turn.status == "failed"
        assert second_turn.status == "collecting"


async def test_recovery_cron_reserves_due_turn_to_avoid_duplicate_enqueue(monkeypatch):
    started = utc_now() - timedelta(seconds=10)
    enqueued: list[tuple[str, tuple, dict]] = []

    async with session_scope() as session:
        result = await TelegramIntakeService(session, now=lambda: started).ingest_chat_message(
            update_id=1521,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=971,
            text="due",
        )
        turn_id = result.turn.id

    async def fake_enqueue(job_name, *args, **kwargs):
        enqueued.append((job_name, args, kwargs))
        return "job-id"

    monkeypatch.setattr(jobs, "enqueue_job", fake_enqueue)

    first = await jobs.enqueue_due_assistant_turns({})
    second = await jobs.enqueue_due_assistant_turns({})

    assert first == "enqueued 1 assistant turns"
    assert second == "enqueued 0 assistant turns"
    assert len(enqueued) == 1
    async with session_scope() as session:
        turn = await session.get(AssistantTurn, turn_id)
        assert turn.status == "queued"
        assert turn.locked_until is not None


async def test_recovery_cron_reserves_expired_running_turn(monkeypatch):
    started = utc_now() - timedelta(seconds=400)
    enqueued: list[tuple[str, tuple, dict]] = []

    async with session_scope() as session:
        result = await TelegramIntakeService(session, now=lambda: started).ingest_chat_message(
            update_id=1522,
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=972,
            text="stale running",
        )
        turn_id = result.turn.id
        turn = await session.get(AssistantTurn, turn_id)
        turn.status = "running"
        turn.started_at = started
        turn.locked_until = started + timedelta(seconds=60)

    async def fake_enqueue(job_name, *args, **kwargs):
        enqueued.append((job_name, args, kwargs))
        return "job-id"

    monkeypatch.setattr(jobs, "enqueue_job", fake_enqueue)

    summary = await jobs.enqueue_due_assistant_turns({})

    assert summary == "enqueued 1 assistant turns"
    assert len(enqueued) == 1
    assert enqueued[0][1] == (str(turn_id),)
    async with session_scope() as session:
        turn = await session.get(AssistantTurn, turn_id)
        assert turn.status == "queued"
        assert turn.error_message == "turn lock expired; queued for recovery"
        assert turn.locked_until is not None
