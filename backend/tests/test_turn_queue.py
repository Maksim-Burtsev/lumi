from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from lumi.assistant.orchestrator import AssistantResult
from lumi.db.models import AssistantTurn, TelegramUpdate
from lumi.db.session import session_scope
from lumi.services.turns import TelegramIntakeService, TurnService
from lumi.utils.time import utc_now
from lumi.worker import jobs

from .conftest import TEST_TELEGRAM_ID

BASE_NOW = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)


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
