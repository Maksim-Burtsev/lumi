"""LLM provider abstraction. Providers are stateless and DB-free."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


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
    ) -> dict[str, Any]: ...


def estimate_tokens(text: str) -> int:
    """Cheap chars/4 token estimate — good enough for budgets and logging."""
    return max(1, len(text) // 4)
