"""Transient media inputs for assistant turns.

Bytes are passed to the LLM provider for the current request only. Durable
message rows store metadata/file_id, not media bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lumi.llm.base import LLMImagePart

if TYPE_CHECKING:
    from lumi.assistant.schemas import MediaUnderstanding


@dataclass(slots=True)
class ImageInput:
    data: bytes
    mime_type: str
    file_id: str
    file_unique_id: str | None = None
    file_size: int | None = None
    file_name: str | None = None
    width: int | None = None
    height: int | None = None
    source: str = "attached"
    telegram_message_id: int | None = None

    def to_llm_part(self) -> LLMImagePart:
        return LLMImagePart(data=self.data, mime_type=self.mime_type)

    def to_metadata(self) -> dict:
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
        }
        return {k: v for k, v in data.items() if v is not None}


def media_candidate_id(source: str, metadata: dict[str, Any]) -> str:
    key = (
        metadata.get("file_unique_id")
        or metadata.get("file_id")
        or metadata.get("telegram_message_id")
        or "unknown"
    )
    return f"{source}:{key}"


@dataclass(slots=True)
class MediaCandidate:
    id: str
    source: str
    metadata: dict[str, Any]
    media_context: MediaUnderstanding | None = None
    image: ImageInput | None = None

    def to_prompt_text(self) -> str:
        lines = [
            f"- media_id: {self.id}",
            f"  source: {self.source}",
            f"  telegram_message_id: {self.metadata.get('telegram_message_id') or '—'}",
            f"  mime_type: {self.metadata.get('mime_type') or '—'}",
            f"  has_file_id: {'yes' if self.metadata.get('file_id') else 'no'}",
            f"  has_media_context: {'yes' if self.media_context else 'no'}",
        ]
        if self.media_context is not None:
            media_lines = self.media_context.to_prompt_text().splitlines()
            lines.append("  media_context:")
            lines.extend(f"    {line}" for line in media_lines)
        return "\n".join(lines)
