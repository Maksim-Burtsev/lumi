"""Telegram image extraction and transient download helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.media import ImageInput
from lumi.config import get_settings
from lumi.db.models import Message, MessageRole

SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


class ImageDownloadError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class TelegramImageRef:
    file_id: str
    file_unique_id: str | None = None
    mime_type: str = "image/jpeg"
    file_size: int | None = None
    file_name: str | None = None
    width: int | None = None
    height: int | None = None
    source: str = "attached"
    telegram_message_id: int | None = None


def extract_image_ref(message: Any, *, source: str = "attached") -> TelegramImageRef | None:
    photos = list(getattr(message, "photo", None) or [])
    if photos:
        photo = max(photos, key=lambda p: getattr(p, "file_size", None) or getattr(p, "width", 0) * getattr(p, "height", 0))
        return TelegramImageRef(
            file_id=photo.file_id,
            file_unique_id=getattr(photo, "file_unique_id", None),
            mime_type="image/jpeg",
            file_size=getattr(photo, "file_size", None),
            width=getattr(photo, "width", None),
            height=getattr(photo, "height", None),
            source=source,
            telegram_message_id=getattr(message, "message_id", None),
        )

    document = getattr(message, "document", None)
    if document is None:
        return None
    mime_type = getattr(document, "mime_type", None)
    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        return None
    return TelegramImageRef(
        file_id=document.file_id,
        file_unique_id=getattr(document, "file_unique_id", None),
        mime_type=mime_type,
        file_size=getattr(document, "file_size", None),
        file_name=getattr(document, "file_name", None),
        source=source,
        telegram_message_id=getattr(message, "message_id", None),
    )


async def find_latest_image_metadata(session: AsyncSession, conversation_id) -> dict[str, Any] | None:
    result = await session.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role == MessageRole.USER,
            Message.metadata_["images"].is_not(None),
        )
        .order_by(Message.created_at.desc())
        .limit(50)
    )
    for message in result.scalars():
        images = (message.metadata_ or {}).get("images") or []
        if images:
            return images[0]
    return None


def ref_from_metadata(metadata: dict[str, Any], *, source: str = "latest") -> TelegramImageRef | None:
    file_id = metadata.get("file_id")
    if not file_id:
        return None
    return TelegramImageRef(
        file_id=file_id,
        file_unique_id=metadata.get("file_unique_id"),
        mime_type=metadata.get("mime_type") or "image/jpeg",
        file_size=metadata.get("file_size"),
        file_name=metadata.get("file_name"),
        width=metadata.get("width"),
        height=metadata.get("height"),
        source=source,
        telegram_message_id=metadata.get("telegram_message_id"),
    )


async def download_image_input(bot: Any, ref: TelegramImageRef) -> ImageInput:
    max_bytes = get_settings().telegram_image_max_bytes
    if ref.file_size is not None and ref.file_size > max_bytes:
        raise ImageDownloadError(f"image is too large: {ref.file_size} bytes")
    tg_file = await bot.get_file(ref.file_id)
    file_path = getattr(tg_file, "file_path", None)
    if not file_path:
        raise ImageDownloadError("telegram did not return file_path")
    downloaded = await bot.download_file(file_path)
    if isinstance(downloaded, bytes | bytearray):
        data = bytes(downloaded)
    elif hasattr(downloaded, "read"):
        data = downloaded.read()
    else:
        raise ImageDownloadError("telegram returned unsupported file object")
    if len(data) > max_bytes:
        raise ImageDownloadError(f"image is too large: {len(data)} bytes")
    return ImageInput(
        data=data,
        mime_type=ref.mime_type,
        file_id=ref.file_id,
        file_unique_id=ref.file_unique_id,
        file_size=ref.file_size or len(data),
        file_name=ref.file_name,
        width=ref.width,
        height=ref.height,
        source=ref.source,
        telegram_message_id=ref.telegram_message_id,
    )
