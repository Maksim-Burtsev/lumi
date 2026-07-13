"""Telegram attachment classification for product-scope rejection and audit."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


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
    media_group_id: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        data = {
            "file_id": self.file_id,
            "file_unique_id": self.file_unique_id,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "file_name": self.file_name,
            "width": self.width,
            "height": self.height,
            "source": self.source,
            "telegram_message_id": self.telegram_message_id,
            "media_group_id": self.media_group_id,
        }
        return {key: value for key, value in data.items() if value is not None}

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any], *, source: str | None = None) -> TelegramImageRef | None:
        file_id = metadata.get("file_id")
        if not file_id:
            return None
        mime_type = metadata.get("mime_type") or "image/jpeg"
        if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
            return None
        return cls(
            file_id=file_id,
            file_unique_id=metadata.get("file_unique_id"),
            mime_type=mime_type,
            file_size=metadata.get("file_size"),
            file_name=metadata.get("file_name"),
            width=metadata.get("width"),
            height=metadata.get("height"),
            source=source or metadata.get("source") or "attached",
            telegram_message_id=metadata.get("telegram_message_id"),
            media_group_id=metadata.get("media_group_id"),
        )


@dataclass(frozen=True, slots=True)
class ClassifiedAttachmentMessage:
    chat_id: int
    message_id: int
    text: str = ""
    media_group_id: str | None = None
    image_ref: TelegramImageRef | None = None
    ignored_attachments: list[dict[str, Any]] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "message_id": self.message_id,
            "text": self.text,
            "media_group_id": self.media_group_id,
            "image": self.image_ref.to_metadata() if self.image_ref else None,
            "ignored_attachments": list(self.ignored_attachments or []),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ClassifiedAttachmentMessage:
        image_payload = payload.get("image")
        return cls(
            chat_id=int(payload["chat_id"]),
            message_id=int(payload["message_id"]),
            text=str(payload.get("text") or ""),
            media_group_id=payload.get("media_group_id"),
            image_ref=TelegramImageRef.from_metadata(image_payload) if image_payload else None,
            ignored_attachments=list(payload.get("ignored_attachments") or []),
        )


@dataclass(frozen=True, slots=True)
class LogicalMessage:
    chat_id: int
    primary_message_id: int
    text: str
    media_group_id: str | None = None
    supported_images: list[TelegramImageRef] | None = None
    unsupported_attachments: list[dict[str, Any]] | None = None
    rejection_reason: str | None = None
    telegram_message_ids: list[int] | None = None

    @property
    def image_ref(self) -> TelegramImageRef | None:
        images = list(self.supported_images or [])
        if self.is_rejected or len(images) != 1:
            return None
        return images[0]

    @property
    def ignored_attachments(self) -> list[dict[str, Any]]:
        return list(self.unsupported_attachments or [])

    @property
    def has_supported_image(self) -> bool:
        return bool(self.supported_images)

    @property
    def has_unsupported_attachments(self) -> bool:
        return bool(self.unsupported_attachments)

    @property
    def is_rejected(self) -> bool:
        return self.rejection_reason is not None


def extract_image_ref(message: Any, *, source: str = "attached") -> TelegramImageRef | None:
    media_group_id = getattr(message, "media_group_id", None)
    photos = list(getattr(message, "photo", None) or [])
    if photos:
        photo = max(
            photos,
            key=lambda p: getattr(p, "file_size", None)
            or getattr(p, "width", 0) * getattr(p, "height", 0),
        )
        return TelegramImageRef(
            file_id=photo.file_id,
            file_unique_id=getattr(photo, "file_unique_id", None),
            mime_type="image/jpeg",
            file_size=getattr(photo, "file_size", None),
            width=getattr(photo, "width", None),
            height=getattr(photo, "height", None),
            source=source,
            telegram_message_id=getattr(message, "message_id", None),
            media_group_id=media_group_id,
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
        media_group_id=media_group_id,
    )


def extract_ignored_attachment_metadata(
    message: Any,
    *,
    source: str = "attached",
) -> dict[str, Any] | None:
    attachment = getattr(message, "document", None) or getattr(message, "video", None)
    if attachment is None:
        return None
    mime_type = getattr(attachment, "mime_type", None)
    if mime_type in SUPPORTED_IMAGE_MIME_TYPES:
        return None
    data = {
        "file_id": getattr(attachment, "file_id", None),
        "file_unique_id": getattr(attachment, "file_unique_id", None),
        "mime_type": mime_type,
        "file_size": getattr(attachment, "file_size", None),
        "file_name": getattr(attachment, "file_name", None),
        "source": source,
        "telegram_message_id": getattr(message, "message_id", None),
        "media_group_id": getattr(message, "media_group_id", None),
        "reason": "unsupported_mime_type",
    }
    return {key: value for key, value in data.items() if value is not None}


def classify_attachment_message(message: Any) -> ClassifiedAttachmentMessage:
    ignored = extract_ignored_attachment_metadata(message)
    return ClassifiedAttachmentMessage(
        chat_id=int(message.chat.id),
        message_id=int(message.message_id),
        text=(getattr(message, "text", None) or getattr(message, "caption", None) or "").strip(),
        media_group_id=getattr(message, "media_group_id", None),
        image_ref=extract_image_ref(message),
        ignored_attachments=[ignored] if ignored is not None else [],
    )


def build_logical_message(items: list[ClassifiedAttachmentMessage]) -> LogicalMessage:
    if not items:
        raise ValueError("logical message requires at least one item")
    sorted_items = sorted(items, key=lambda item: item.message_id)
    text = next((item.text for item in sorted_items if item.text), "")
    image_refs = [item.image_ref for item in sorted_items if item.image_ref is not None]
    unsupported: list[dict[str, Any]] = []
    for item in sorted_items:
        unsupported.extend(item.ignored_attachments or [])
    first = sorted_items[0]
    rejection_reason = None
    if image_refs and unsupported:
        rejection_reason = "mixed_unsupported_attachment"
    elif unsupported:
        rejection_reason = "unsupported_attachment"
    elif len(image_refs) > 1:
        rejection_reason = "multiple_supported_images"
    primary_message_id = first.message_id
    if (
        rejection_reason is None
        and len(image_refs) == 1
        and image_refs[0].telegram_message_id is not None
    ):
        primary_message_id = image_refs[0].telegram_message_id
    return LogicalMessage(
        chat_id=first.chat_id,
        primary_message_id=primary_message_id,
        text=text,
        media_group_id=first.media_group_id,
        supported_images=image_refs,
        unsupported_attachments=unsupported,
        rejection_reason=rejection_reason,
        telegram_message_ids=[item.message_id for item in sorted_items],
    )


class AttachmentBatchBuffer:
    def __init__(
        self,
        redis: Any,
        *,
        window_seconds: float = 1.8,
        ttl_seconds: int = 30,
        key_prefix: str = "lumi:telegram_media_group",
    ) -> None:
        self.redis = redis
        self.window_seconds = window_seconds
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix

    async def add_and_maybe_finalize(
        self,
        item: ClassifiedAttachmentMessage,
    ) -> LogicalMessage | None:
        if not item.media_group_id:
            return build_logical_message([item])
        key = self._key(item)
        lock_key = f"{key}:finalize_lock"
        await self.redis.rpush(key, json.dumps(item.to_payload(), ensure_ascii=False))
        await self.redis.expire(key, self.ttl_seconds)
        await asyncio.sleep(self.window_seconds)
        locked = await self.redis.set(lock_key, str(item.message_id), nx=True, ex=self.ttl_seconds)
        if not locked:
            return None
        raw_items = await self.redis.lrange(key, 0, -1)
        await self.redis.delete(key)
        items = [
            ClassifiedAttachmentMessage.from_payload(json.loads(
                raw.decode("utf-8") if isinstance(raw, bytes | bytearray) else raw
            ))
            for raw in raw_items
        ]
        return build_logical_message(items)

    def _key(self, item: ClassifiedAttachmentMessage) -> str:
        return f"{self.key_prefix}:{item.chat_id}:{item.media_group_id}"
