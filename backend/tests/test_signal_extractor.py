import uuid
from types import SimpleNamespace

from lumi.assistant.signal_extractor import SignalExtractor
from lumi.llm.base import LLMResponse
from lumi.llm.gateway import LLMGateway
from lumi.llm.mock import MockLLMProvider


def _test_user():
    return SimpleNamespace(id=uuid.uuid4(), timezone="Europe/Moscow")


class GarbageProvider:
    """Returns non-JSON garbage — extraction must degrade to empty signals."""

    name = "garbage"
    model = "garbage-1"

    async def complete(self, **kwargs) -> LLMResponse:
        return LLMResponse(text="ну тут никакого джейсона нет", provider=self.name,
                           model=self.model, latency_ms=1, input_chars=1, output_chars=10)

    async def complete_json(self, **kwargs) -> dict:
        raise ValueError("no json")


async def test_extracts_task_with_reminder():
    u = _test_user()
    extractor = SignalExtractor(LLMGateway(MockLLMProvider()))
    signals = await extractor.extract(user=u, text="Напомни завтра в 10 написать Саше")
    assert len(signals.tasks) == 1
    task = signals.tasks[0]
    assert "саше" in task.title.lower()
    assert task.reminder_at_local is not None
    assert task.reminder_at_local.hour == 10
    assert task.confidence >= 0.85


async def test_extracts_memory_candidate():
    u = _test_user()
    extractor = SignalExtractor(LLMGateway(MockLLMProvider()))
    signals = await extractor.extract(user=u, text="Запомни: дайджесты лучше до 09:30")
    assert len(signals.memory_candidates) == 1
    assert "09:30" in signals.memory_candidates[0].text


async def test_garbage_output_degrades_gracefully():
    u = _test_user()
    extractor = SignalExtractor(LLMGateway(GarbageProvider()))
    signals = await extractor.extract(user=u, text="Напомни завтра в 10 написать Саше")
    assert signals.tasks == []
    assert signals.should_answer_normally is True


async def test_plain_chat_no_actions():
    u = _test_user()
    extractor = SignalExtractor(LLMGateway(MockLLMProvider()))
    signals = await extractor.extract(user=u, text="Как дела?")
    assert signals.tasks == []
    assert signals.memory_candidates == []


async def test_extracts_action_only_backlog_task():
    u = _test_user()
    extractor = SignalExtractor(LLMGateway(MockLLMProvider()))
    signals = await extractor.extract(
        user=u,
        text="добавь в бэклог задачу свой аналог session в Lumi интегрировать",
    )
    assert len(signals.tasks) == 1
    assert signals.tasks[0].title == "Свой аналог session в Lumi интегрировать"
    assert signals.tasks[0].requires_confirmation is True
    assert signals.should_answer_normally is False


async def test_extracts_task_rename_update():
    u = _test_user()
    extractor = SignalExtractor(LLMGateway(MockLLMProvider()))
    signals = await extractor.extract(
        user=u,
        text=(
            "Задачу «Написать короткий сценарий теста accept/reject» переименуй "
            "в «Свой аналог session в Lumi интегрировать»"
        ),
    )
    assert signals.tasks == []
    assert len(signals.task_updates) == 1
    update = signals.task_updates[0]
    assert update.operation == "rename"
    assert update.current_title == "Написать короткий сценарий теста accept/reject"
    assert update.new_title == "Свой аналог session в Lumi интегрировать"
    assert update.requires_confirmation is False
    assert signals.should_answer_normally is False
