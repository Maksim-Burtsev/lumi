import asyncio
from types import SimpleNamespace

from sqlalchemy import select

from lumi.bot import handlers
from lumi.db.models import AssistantTurn, Message, MessageRole
from lumi.db.session import session_scope

from .conftest import TEST_TELEGRAM_ID


class FakeTelegramMessage:
    def __init__(
        self,
        *,
        message_id: int,
        text: str | None = None,
        caption: str | None = None,
        photo: list | None = None,
        document=None,
        video=None,
        media_group_id: str | None = None,
        language_code: str | None = None,
    ) -> None:
        self.message_id = message_id
        self.text = text
        self.caption = caption
        self.photo = photo or []
        self.document = document
        self.video = video
        self.media_group_id = media_group_id
        self.reply_to_message = None
        self.chat = SimpleNamespace(id=TEST_TELEGRAM_ID, type="private")
        self.from_user = SimpleNamespace(
            id=TEST_TELEGRAM_ID,
            username="tester",
            first_name="Test",
            last_name="User",
            language_code=language_code,
        )
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs):
        self.answers.append(text)
        return SimpleNamespace(
            edit_text=self._edit_text,
            delete=self._delete,
        )

    async def _edit_text(self, text: str, **kwargs) -> None:
        self.answers.append(text)

    async def _delete(self) -> None:
        return None


class FakeBot:
    def __init__(self) -> None:
        self.actions: list[tuple[int, str]] = []

    async def send_chat_action(self, *, chat_id: int, action: str) -> None:
        self.actions.append((chat_id, action))


async def test_rejected_unsupported_attachment_with_caption_does_not_call_llm_or_download(monkeypatch):
    orchestrator_called = False
    download_called = False

    async def fake_check_allowed(*args, **kwargs):
        return True

    monkeypatch.setattr(handlers, "_check_allowed", fake_check_allowed)

    message = FakeTelegramMessage(
        message_id=501,
        caption="создай задачу из документа",
        document=SimpleNamespace(
            file_id="pdf-file",
            file_unique_id="pdf-unique",
            mime_type="application/pdf",
            file_size=1200,
            file_name="scan.pdf",
        ),
    )

    await handlers.on_chat_message(message, FakeBot())

    assert message.answers == [handlers.REJECTED_ATTACHMENT_REPLY]
    assert orchestrator_called is False
    assert download_called is False

    async with session_scope() as session:
        inbound = (
            await session.execute(
                select(Message).where(
                    Message.role == MessageRole.USER,
                    Message.telegram_message_id == 501,
                )
            )
        ).scalars().one()
        outbound = (
            await session.execute(select(Message).where(Message.role == MessageRole.ASSISTANT))
        ).scalars().one()

    assert inbound.content == "создай задачу из документа"
    assert inbound.content_json["attachment_rejection"]["reason"] == "unsupported_attachment"
    assert inbound.content_json["unsupported_attachments"][0]["file_name"] == "scan.pdf"
    assert "images" not in inbound.content_json
    assert outbound.content == handlers.REJECTED_ATTACHMENT_REPLY


async def test_rejected_multiple_supported_images_does_not_download_first_image(monkeypatch):
    download_called = False

    async def fake_check_allowed(*args, **kwargs):
        return True

    monkeypatch.setattr(handlers, "_check_allowed", fake_check_allowed)

    message = FakeTelegramMessage(
        message_id=502,
        media_group_id="album-multi",
        photo=[SimpleNamespace(file_id="first", file_unique_id="img-1", file_size=100, width=1, height=1)],
    )
    second = FakeTelegramMessage(
        message_id=503,
        media_group_id="album-multi",
        photo=[SimpleNamespace(file_id="second", file_unique_id="img-2", file_size=100, width=1, height=1)],
    )

    class FakeRedis:
        def __init__(self) -> None:
            self.values: list[str] = []
            self.locked = False

        async def rpush(self, key: str, value: str) -> None:
            self.values.append(value)

        async def expire(self, key: str, seconds: int) -> None:
            return None

        async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
            if self.locked:
                return False
            self.locked = True
            return True

        async def lrange(self, key: str, start: int, end: int) -> list[str]:
            return self.values

        async def delete(self, *keys: str) -> None:
            return None

    redis = FakeRedis()

    async def fake_get_queue():
        return redis

    def fake_buffer_init(self, redis):
        self.redis = redis
        self.window_seconds = 0
        self.ttl_seconds = 30
        self.key_prefix = "test"

    monkeypatch.setattr(handlers, "get_queue", fake_get_queue)
    monkeypatch.setattr(handlers.AttachmentBatchBuffer, "__init__", fake_buffer_init)

    await asyncio.gather(
        handlers.on_chat_message(message, FakeBot()),
        handlers.on_chat_message(second, FakeBot()),
    )

    answers = message.answers + second.answers
    assert answers == [handlers.REJECTED_ATTACHMENT_REPLY]
    assert download_called is False

    async with session_scope() as session:
        inbound = (
            await session.execute(
                select(Message).where(
                    Message.role == MessageRole.USER,
                    Message.telegram_message_id == 502,
                )
            )
        ).scalars().one()

    assert inbound.content_json["attachment_rejection"]["reason"] == "multiple_supported_images"
    assert [item["file_id"] for item in inbound.content_json["rejected_supported_images"]] == ["first", "second"]
    assert "images" not in inbound.content_json


async def test_chat_message_enqueues_turn_without_inline_orchestrator(monkeypatch):
    enqueued: list[tuple[str, tuple, dict]] = []

    async def fake_check_allowed(*args, **kwargs):
        return True

    async def fake_enqueue(job_name, *args, **kwargs):
        enqueued.append((job_name, args, kwargs))
        return "job-id"

    monkeypatch.setattr(handlers, "_check_allowed", fake_check_allowed)
    monkeypatch.setattr(handlers, "enqueue_job", fake_enqueue)

    message = FakeTelegramMessage(message_id=901, text="поставь задачу", language_code="en-US")

    await handlers.on_chat_message(message, FakeBot())

    assert message.answers == ["⏳"]
    assert len(enqueued) == 1
    assert enqueued[0][0] == "process_assistant_turn"

    async with session_scope() as session:
        turn = (await session.execute(select(AssistantTurn))).scalars().one()
        user = await handlers.UserService(session).get_by_telegram_id(TEST_TELEGRAM_ID)
    assert turn.input_text == "поставь задачу"
    assert turn.primary_message_id == 901
    assert user.language_code == "en-US"
    assert user.locale == "en"


async def test_duplicate_enqueue_does_not_show_queue_unavailable(monkeypatch):
    async def fake_check_allowed(*args, **kwargs):
        return True

    async def fake_enqueue(job_name, *args, **kwargs):
        return None

    monkeypatch.setattr(handlers, "_check_allowed", fake_check_allowed)
    monkeypatch.setattr(handlers, "enqueue_job", fake_enqueue)

    message = FakeTelegramMessage(message_id=902, text="быстрый дубль enqueue")

    await handlers.on_chat_message(message, FakeBot())

    assert message.answers == ["⏳"]
