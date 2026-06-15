from io import BytesIO
from types import SimpleNamespace

from lumi.bot.media import (
    TelegramImageRef,
    download_image_input,
    extract_image_ref,
    find_latest_image_metadata,
)
from lumi.db.models import Message, MessageRole
from lumi.db.session import session_scope
from lumi.services.users import UserService

from .conftest import TEST_TELEGRAM_ID


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
