"""LLM provider abstraction. Providers are stateless and DB-free."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class LLMTextPart:
    text: str


@dataclass(slots=True)
class LLMImagePart:
    data: bytes
    mime_type: str
    detail: str = "default"
    max_long_side_pixel: int | None = None


LLMContent = str | list[LLMTextPart | LLMImagePart]


@dataclass(slots=True)
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: LLMContent


@dataclass(slots=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    latency_ms: int
    input_chars: int
    output_chars: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw: dict[str, Any] | None = field(default=None, repr=False)


class LLMError(Exception):
    """Base error for LLM provider failures."""


class LLMTimeoutError(LLMError):
    pass


class LLMResponseFormatError(LLMError):
    """Model returned something we could not parse as requested."""


class LLMProvider(Protocol):
    name: str

    async def complete(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        request_kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> LLMResponse: ...

    async def complete_json(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        json_schema_hint: dict[str, Any] | None = None,
        request_kind: str,
        metadata: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict[str, Any]: ...


def estimate_tokens(text: str) -> int:
    """Cheap chars/4 token estimate — good enough for budgets and logging."""
    return max(1, len(text) // 4)


def content_to_text(content: LLMContent) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for part in content:
        if isinstance(part, LLMTextPart):
            parts.append(part.text)
        elif isinstance(part, LLMImagePart):
            digest = hashlib.sha256(part.data).hexdigest()[:12]
            parts.append(f"[image {part.mime_type} {len(part.data)} bytes sha256:{digest}]")
    return "\n".join(p for p in parts if p)


def content_char_count(content: LLMContent) -> int:
    if isinstance(content, str):
        return len(content)
    total = 0
    for part in content:
        if isinstance(part, LLMTextPart):
            total += len(part.text)
        elif isinstance(part, LLMImagePart):
            total += len(part.data)
    return total
