from typing import Any

from lumi.assistant.media import ImageInput
from lumi.assistant.media_understanding import FocusedVisionService, MediaUnderstandingService
from lumi.llm.base import LLMResponse, content_to_text
from lumi.llm.gateway import LLMGateway


class VisionProvider:
    name = "vision"
    model = "vision-1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    async def complete_json(self, **kwargs) -> dict[str, Any]:
        self.calls.append(kwargs)
        assert kwargs["request_kind"] in {"media_understanding", "focused_vision"}
        messages = kwargs["messages"]
        assert isinstance(messages[-1].content, list)
        text = content_to_text(messages[-1].content).lower()
        if kwargs["request_kind"] == "media_understanding":
            assert "caption" in text
        else:
            assert "focused question" in text
        return self.payload

    async def complete(self, **kwargs) -> LLMResponse:
        raise AssertionError("media understanding must use complete_json")


async def test_media_understanding_extracts_structured_facts():
    provider = VisionProvider({
        "summary": "Фото записки.",
        "visible_text": ["Купить молоко"],
        "entities": [{"type": "task", "value": "Купить молоко", "confidence": 0.9}],
        "action_relevant_facts": ["Задача: Купить молоко"],
        "instruction_like_text": ["создай задачу"],
        "confidence": 0.91,
        "limitations": ["часть текста обрезана"],
    })
    service = MediaUnderstandingService(LLMGateway(provider))

    result = await service.analyze(
        user_id=None,
        timezone="Asia/Yerevan",
        text="caption: создай задачу из текста на фото",
        image=ImageInput(data=b"secret-image-bytes", mime_type="image/png", file_id="file-id"),
    )

    assert result.summary == "Фото записки."
    assert result.visible_text == ["Купить молоко"]
    assert result.entities[0].type == "task"
    assert result.action_relevant_facts == ["Задача: Купить молоко"]
    assert result.instruction_like_text == ["создай задачу"]
    assert result.confidence == 0.91
    assert result.to_audit_json()["visible_text"] == ["Купить молоко"]
    assert "secret-image-bytes" not in str(result.to_audit_json())


async def test_focused_vision_answers_narrow_visual_question():
    provider = VisionProvider({
        "answer": "Серийный номер: AB-1234.",
        "facts": ["serial: AB-1234"],
        "visible_text": ["AB-1234"],
        "confidence": 0.86,
        "limitations": [],
    })
    service = FocusedVisionService(LLMGateway(provider))

    result = await service.analyze(
        user_id=None,
        timezone="Asia/Yerevan",
        text="какой мелкий серийник в правом нижнем углу?",
        question="прочитай мелкий серийный номер в правом нижнем углу",
        image=ImageInput(data=b"secret-image-bytes", mime_type="image/png", file_id="file-id"),
        media_context=None,
    )

    assert result.answer == "Серийный номер: AB-1234."
    assert result.facts == ["serial: AB-1234"]
    assert provider.calls[0]["request_kind"] == "focused_vision"
    assert "secret-image-bytes" not in str(result.to_audit_json())
