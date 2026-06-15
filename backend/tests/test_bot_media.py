import asyncio
from io import BytesIO
from types import SimpleNamespace

import pytest

from lumi.bot.media import (
    AttachmentBatchBuffer,
    ImageTooLargeError,
    TelegramImageRef,
    build_logical_message,
    classify_attachment_message,
    download_image_input,
    extract_ignored_attachment_metadata,
    extract_image_ref,
    find_latest_image_metadata,
    ref_from_metadata,
)
from lumi.db.models import Message, MessageRole
from lumi.db.session import session_scope
from lumi.services.users import UserService

from .conftest import TEST_TELEGRAM_ID


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.locks: set[str] = set()

    async def rpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).append(value)

    async def expire(self, key: str, seconds: int) -> None:
        return None

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.locks:
            return False
        self.locks.add(key)
        return True

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        values = self.lists.get(key, [])
        return values[start:] if end == -1 else values[start : end + 1]

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.lists.pop(key, None)
            self.locks.discard(key)


def test_extract_image_ref_prefers_largest_photo():
    message = SimpleNamespace(
        message_id=10,
        photo=[
            SimpleNamespace(file_id="small", file_unique_id="u1", file_size=100, width=100, height=100),
            SimpleNamespace(file_id="large", file_unique_id="u2", file_size=500, width=800, height=600),
        ],
        document=None,
    )

    ref = extract_image_ref(message)

    assert ref == TelegramImageRef(
        file_id="large",
        file_unique_id="u2",
        mime_type="image/jpeg",
        file_size=500,
        file_name=None,
        width=800,
        height=600,
        source="attached",
        telegram_message_id=10,
    )


def test_classify_attachment_message_includes_media_group_id_for_image_and_unsupported_document():
    image_message = SimpleNamespace(
        message_id=10,
        chat=SimpleNamespace(id=42),
        media_group_id="album-1",
        text=None,
        caption="что тут?",
        photo=[
            SimpleNamespace(file_id="small", file_unique_id="u1", file_size=100, width=100, height=100),
            SimpleNamespace(file_id="large", file_unique_id="u2", file_size=500, width=800, height=600),
        ],
        document=None,
        video=None,
    )
    pdf_message = SimpleNamespace(
        message_id=11,
        chat=SimpleNamespace(id=42),
        media_group_id="album-1",
        text=None,
        caption=None,
        photo=[],
        document=SimpleNamespace(
            file_id="pdf-file",
            file_unique_id="pdf-unique",
            mime_type="application/pdf",
            file_size=1200,
            file_name="scan.pdf",
        ),
        video=None,
    )

    image_item = classify_attachment_message(image_message)
    pdf_item = classify_attachment_message(pdf_message)

    assert image_item.media_group_id == "album-1"
    assert image_item.text == "что тут?"
    assert image_item.image_ref is not None
    assert image_item.image_ref.media_group_id == "album-1"
    assert pdf_item.ignored_attachments == [{
        "file_id": "pdf-file",
        "file_unique_id": "pdf-unique",
        "mime_type": "application/pdf",
        "file_size": 1200,
        "file_name": "scan.pdf",
        "source": "attached",
        "telegram_message_id": 11,
        "media_group_id": "album-1",
        "reason": "unsupported_mime_type",
    }]


def test_build_logical_message_rejects_multiple_supported_images():
    first = classify_attachment_message(SimpleNamespace(
        message_id=20,
        chat=SimpleNamespace(id=42),
        media_group_id="album-2",
        text=None,
        caption=None,
        photo=[SimpleNamespace(file_id="first", file_unique_id="img-1", file_size=100, width=1, height=1)],
        document=None,
        video=None,
    ))
    second = classify_attachment_message(SimpleNamespace(
        message_id=21,
        chat=SimpleNamespace(id=42),
        media_group_id="album-2",
        text=None,
        caption="caption from second",
        photo=[SimpleNamespace(file_id="second", file_unique_id="img-2", file_size=100, width=1, height=1)],
        document=None,
        video=None,
    ))
    third = classify_attachment_message(SimpleNamespace(
        message_id=22,
        chat=SimpleNamespace(id=42),
        media_group_id="album-2",
        text=None,
        caption=None,
        photo=[SimpleNamespace(file_id="third", file_unique_id="img-3", file_size=100, width=1, height=1)],
        document=None,
        video=None,
    ))

    logical = build_logical_message([third, second, first])

    assert logical.is_rejected is True
    assert logical.rejection_reason == "multiple_supported_images"
    assert logical.image_ref is None
    assert [image.file_id for image in logical.supported_images] == ["first", "second", "third"]
    assert logical.ignored_attachments == []


def test_build_logical_message_rejects_mixed_supported_image_and_unsupported_attachment():
    image = classify_attachment_message(SimpleNamespace(
        message_id=20,
        chat=SimpleNamespace(id=42),
        media_group_id="album-2",
        text=None,
        caption=None,
        photo=[SimpleNamespace(file_id="first", file_unique_id="img-1", file_size=100, width=1, height=1)],
        document=None,
        video=None,
    ))
    pdf = classify_attachment_message(SimpleNamespace(
        message_id=22,
        chat=SimpleNamespace(id=42),
        media_group_id="album-2",
        text=None,
        caption=None,
        photo=[],
        document=SimpleNamespace(
            file_id="pdf",
            file_unique_id="pdf-u",
            mime_type="application/pdf",
            file_size=1,
            file_name="file.pdf",
        ),
        video=None,
    ))

    logical = build_logical_message([pdf, image])

    assert logical.is_rejected is True
    assert logical.rejection_reason == "mixed_unsupported_attachment"
    assert logical.image_ref is None
    assert [image.file_id for image in logical.supported_images] == ["first"]
    assert [item["reason"] for item in logical.ignored_attachments] == ["unsupported_mime_type"]


def test_build_logical_message_rejects_unsupported_attachment_with_caption():
    pdf = classify_attachment_message(SimpleNamespace(
        message_id=23,
        chat=SimpleNamespace(id=42),
        media_group_id=None,
        text=None,
        caption="создай задачу из документа",
        photo=[],
        document=SimpleNamespace(
            file_id="pdf",
            file_unique_id="pdf-u",
            mime_type="application/pdf",
            file_size=1,
            file_name="file.pdf",
        ),
        video=None,
    ))

    logical = build_logical_message([pdf])

    assert logical.text == "создай задачу из документа"
    assert logical.is_rejected is True
    assert logical.rejection_reason == "unsupported_attachment"
    assert logical.image_ref is None
    assert logical.supported_images == []
    assert [item["reason"] for item in logical.ignored_attachments] == ["unsupported_mime_type"]


@pytest.mark.parametrize(
    ("mime_type", "file_name", "field"),
    [
        ("application/zip", "archive.zip", "document"),
        ("image/gif", "image.gif", "document"),
        ("image/heic", "image.heic", "document"),
        ("video/mp4", None, "video"),
    ],
)
def test_build_logical_message_rejects_unsupported_attachment_types_with_caption(
    mime_type: str,
    file_name: str | None,
    field: str,
):
    attachment = SimpleNamespace(
        file_id="file",
        file_unique_id="file-u",
        mime_type=mime_type,
        file_size=1,
        file_name=file_name,
    )
    message = SimpleNamespace(
        message_id=25,
        chat=SimpleNamespace(id=42),
        media_group_id=None,
        text=None,
        caption="обработай текст",
        photo=[],
        document=attachment if field == "document" else None,
        video=attachment if field == "video" else None,
    )

    logical = build_logical_message([classify_attachment_message(message)])

    assert logical.is_rejected is True
    assert logical.rejection_reason == "unsupported_attachment"
    assert logical.image_ref is None
    assert logical.unsupported_attachments[0]["mime_type"] == mime_type


def test_build_logical_message_accepts_single_supported_image_with_caption():
    item = classify_attachment_message(SimpleNamespace(
        message_id=24,
        chat=SimpleNamespace(id=42),
        media_group_id=None,
        text=None,
        caption="что тут?",
        photo=[SimpleNamespace(file_id="image", file_unique_id="image-u", file_size=100, width=1, height=1)],
        document=None,
        video=None,
    ))

    logical = build_logical_message([item])

    assert logical.is_rejected is False
    assert logical.rejection_reason is None
    assert logical.image_ref is not None
    assert logical.image_ref.file_id == "image"
    assert [image.file_id for image in logical.supported_images] == ["image"]


async def test_attachment_batch_buffer_returns_one_logical_message_per_media_group():
    redis = FakeRedis()
    buffer = AttachmentBatchBuffer(redis, window_seconds=0)
    first = classify_attachment_message(SimpleNamespace(
        message_id=30,
        chat=SimpleNamespace(id=42),
        media_group_id="album-3",
        text=None,
        caption=None,
        photo=[],
        document=SimpleNamespace(
            file_id="zip",
            file_unique_id="zip-u",
            mime_type="application/zip",
            file_size=100,
            file_name="archive.zip",
        ),
        video=None,
    ))
    second = classify_attachment_message(SimpleNamespace(
        message_id=31,
        chat=SimpleNamespace(id=42),
        media_group_id="album-3",
        text=None,
        caption=None,
        photo=[],
        document=SimpleNamespace(
            file_id="pdf",
            file_unique_id="pdf-u",
            mime_type="application/pdf",
            file_size=100,
            file_name="file.pdf",
        ),
        video=None,
    ))

    first_result, second_result = await asyncio.gather(
        buffer.add_and_maybe_finalize(first),
        buffer.add_and_maybe_finalize(second),
    )

    results = [result for result in (first_result, second_result) if result is not None]
    assert len(results) == 1
    assert [item["file_name"] for item in results[0].ignored_attachments] == ["archive.zip", "file.pdf"]


def test_extract_image_ref_accepts_supported_image_document():
    message = SimpleNamespace(
        message_id=11,
        photo=[],
        document=SimpleNamespace(
            file_id="doc-image",
            file_unique_id="du1",
            mime_type="image/webp",
            file_size=1200,
            file_name="image.webp",
        ),
    )

    ref = extract_image_ref(message)

    assert ref is not None
    assert ref.file_id == "doc-image"
    assert ref.mime_type == "image/webp"
    assert ref.file_name == "image.webp"


@pytest.mark.parametrize("mime_type", ["image/gif", "image/heic", "application/pdf", "video/mp4"])
def test_extract_image_ref_skips_unsupported_document_mime_types(mime_type: str):
    message = SimpleNamespace(
        message_id=12,
        photo=[],
        document=SimpleNamespace(
            file_id="doc-file",
            file_unique_id="du2",
            mime_type=mime_type,
            file_size=1200,
            file_name="upload.bin",
        ),
    )

    assert extract_image_ref(message) is None


def test_extract_ignored_attachment_metadata_records_unsupported_document():
    message = SimpleNamespace(
        message_id=13,
        photo=[],
        document=SimpleNamespace(
            file_id="doc-pdf",
            file_unique_id="pdf-unique",
            mime_type="application/pdf",
            file_size=1200,
            file_name="scan.pdf",
        ),
    )

    metadata = extract_ignored_attachment_metadata(message)

    assert metadata == {
        "file_id": "doc-pdf",
        "file_unique_id": "pdf-unique",
        "mime_type": "application/pdf",
        "file_size": 1200,
        "file_name": "scan.pdf",
        "source": "attached",
        "telegram_message_id": 13,
        "reason": "unsupported_mime_type",
    }


def test_extract_ignored_attachment_metadata_records_unsupported_video():
    message = SimpleNamespace(
        message_id=14,
        media_group_id="album-video",
        photo=[],
        document=None,
        video=SimpleNamespace(
            file_id="video-file",
            file_unique_id="video-unique",
            mime_type="video/mp4",
            file_size=1200,
            file_name=None,
        ),
    )

    metadata = extract_ignored_attachment_metadata(message)

    assert metadata == {
        "file_id": "video-file",
        "file_unique_id": "video-unique",
        "mime_type": "video/mp4",
        "file_size": 1200,
        "source": "attached",
        "telegram_message_id": 14,
        "media_group_id": "album-video",
        "reason": "unsupported_mime_type",
    }


def test_ref_from_metadata_rejects_unsupported_legacy_mime_type():
    assert ref_from_metadata({
        "file_id": "legacy-gif",
        "mime_type": "image/gif",
        "file_size": 100,
    }) is None


async def test_download_image_input_uses_file_id_without_storing_bytes():
    class FakeBot:
        async def get_file(self, file_id: str):
            assert file_id == "file-1"
            return SimpleNamespace(file_path="photos/file.jpg")

        async def download_file(self, file_path: str):
            assert file_path == "photos/file.jpg"
            return BytesIO(b"image-bytes")

    image = await download_image_input(
        FakeBot(),
        TelegramImageRef(
            file_id="file-1",
            file_unique_id="unique-1",
            mime_type="image/jpeg",
            file_size=11,
            source="attached",
            telegram_message_id=42,
        ),
    )

    assert image.data == b"image-bytes"
    assert image.to_metadata()["file_id"] == "file-1"
    assert "data" not in image.to_metadata()


async def test_download_image_input_rejects_declared_oversize_before_download():
    class FakeBot:
        async def get_file(self, file_id: str):  # pragma: no cover - should not be called
            raise AssertionError("oversized image should be rejected before Telegram download")

    with pytest.raises(ImageTooLargeError):
        await download_image_input(
            FakeBot(),
            TelegramImageRef(
                file_id="file-oversized",
                mime_type="image/png",
                file_size=10_000_001,
            ),
        )


async def test_download_image_input_rejects_actual_oversize_after_download():
    class FakeBot:
        async def get_file(self, file_id: str):
            assert file_id == "file-actual-oversized"
            return SimpleNamespace(file_path="documents/big.png")

        async def download_file(self, file_path: str):
            assert file_path == "documents/big.png"
            return BytesIO(b"x" * 10_000_001)

    with pytest.raises(ImageTooLargeError):
        await download_image_input(
            FakeBot(),
            TelegramImageRef(
                file_id="file-actual-oversized",
                mime_type="image/png",
                file_size=None,
            ),
        )


async def test_find_latest_image_metadata_for_repeat_requests(user):
    async with session_scope() as session:
        users = UserService(session)
        u = await users.ensure_user(TEST_TELEGRAM_ID)
        conversation = await users.ensure_main_conversation(u)
        session.add(Message(
            conversation_id=conversation.id,
            user_id=u.id,
            role=MessageRole.USER,
            content="[image] Что тут?",
            char_count=17,
            metadata_={"images": [{"file_id": "latest", "mime_type": "image/png", "file_size": 100}]},
        ))

    async with session_scope() as session:
        users = UserService(session)
        u = await users.ensure_user(TEST_TELEGRAM_ID)
        conversation = await users.ensure_main_conversation(u)
        metadata = await find_latest_image_metadata(session, conversation.id)

    assert metadata["file_id"] == "latest"
