"""Deterministic mock LLM provider for tests and keyless local smoke runs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

from lumi.llm.base import LLMMessage, LLMResponse

_CURRENT_DT_RE = re.compile(r"Current datetime:\s*(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})")
_HOUR_RE = re.compile(r"\bв\s+(\d{1,2})(?::(\d{2}))?\b", re.IGNORECASE)


def _parse_context_now(text: str) -> datetime:
    m = _CURRENT_DT_RE.search(text)
    if m:
        return datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}:{m.group(3)}:00")
    return datetime.now().replace(second=0, microsecond=0)


def _extract_user_message(text: str) -> str:
    # Extraction prompts put the raw message after a "Message:" marker.
    marker = text.rfind("Message:")
    if marker != -1:
        return text[marker + len("Message:"):].split("\nReturn JSON", 1)[0].strip()
    return text.strip()


class MockLLMProvider:
    name = "mock"
    model = "mock-1"

    async def complete(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        request_kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> LLMResponse:
        text = self._respond(request_kind, messages)
        input_chars = sum(len(m.content) for m in messages) + len(system or "")
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            latency_ms=1,
            input_chars=input_chars,
            output_chars=len(text),
            input_tokens=input_chars // 4,
            output_tokens=len(text) // 4,
        )

    async def complete_stream(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        request_kind: str,
        metadata: dict[str, Any] | None = None,
        on_delta=None,
        on_thinking=None,
    ) -> LLMResponse:
        """Deterministic streaming: the canned reply arrives in 3 chunks."""
        full = self._respond(request_kind, messages)
        step = max(1, len(full) // 3)
        acc = ""
        for i in range(0, len(full), step):
            acc = full[: i + step]
            if on_delta is not None:
                await on_delta(acc)
        input_chars = sum(len(m.content) for m in messages) + len(system or "")
        return LLMResponse(
            text=full, provider=self.name, model=self.model, latency_ms=3,
            input_chars=input_chars, output_chars=len(full),
            input_tokens=input_chars // 4, output_tokens=len(full) // 4,
        )

    async def complete_json(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        json_schema_hint: dict[str, Any] | None = None,
        request_kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self.complete(
            messages=messages, system=system, request_kind=request_kind, metadata=metadata
        )
        return json.loads(response.text)

    # ------------------------------------------------------------------

    def _respond(self, request_kind: str, messages: list[LLMMessage]) -> str:
        joined = "\n".join(m.content for m in messages)
        if request_kind == "signal_extraction":
            return json.dumps(self._extract_signals(joined), ensure_ascii=False)
        if request_kind == "chat_turn":
            # Combined call: signals extracted from the LAST user message only.
            last_user = messages[-1].content if messages else ""
            return json.dumps(
                {"signals": self._extract_signals(last_user),
                 "reply": "Готово, я это зафиксировал."},
                ensure_ascii=False,
            )
        if request_kind == "compaction":
            return (
                "## Summary\nПользователь обсуждал задачи и планирование дня.\n\n"
                "## Decisions\n- Использовать Lumi как ежедневного ассистента.\n\n"
                "## User preferences\n- Краткие ответы.\n\n"
                "## Active projects\n- Lumi.\n\n"
                "## Open loops\n- Нет.\n\n"
                "## Things to avoid\n- Нет."
            )
        if request_kind == "email_triage":
            return json.dumps(
                {"summary": "Новых важных писем нет.", "threads": [], "telegram_digest": "Почта: новых важных писем нет."},
                ensure_ascii=False,
            )
        if request_kind == "news_digest":
            return "Главное за сегодня\n\nПо вашим темам пока без громких событий. Дайджест собран в тестовом режиме."
        if request_kind == "daily_planning":
            return json.dumps(
                {
                    "summary": "Свободных окон достаточно — предлагаю один фокус-блок утром.",
                    "blocks": [],
                },
                ensure_ascii=False,
            )
        # final_chat / custom / anything else
        return "Готово, я это зафиксировал."

    def _extract_signals(self, joined: str) -> dict[str, Any]:
        message = _extract_user_message(joined)
        lowered = message.lower()
        now = _parse_context_now(joined)

        result: dict[str, Any] = {
            "language": "ru",
            "intents": ["chat"],
            "tasks": [],
            "memory_candidates": [],
            "calendar_requests": [],
            "automation_requests": [],
            "email_requests": [],
            "news_requests": [],
            "should_answer_normally": True,
        }

        if "напомни" in lowered:
            target = now + timedelta(days=1) if "завтра" in lowered else now + timedelta(hours=1)
            hour_match = _HOUR_RE.search(lowered)
            if hour_match:
                target = target.replace(
                    hour=int(hour_match.group(1)), minute=int(hour_match.group(2) or 0)
                )
            title = re.sub(r"напомни(ть)?( мне)?( завтра| сегодня)?( в \d{1,2}(:\d{2})?)?\s*",
                           "", message, flags=re.IGNORECASE).strip(" ,.") or message
            result["intents"] = ["create_task", "create_reminder"]
            result["tasks"] = [
                {
                    "title": title[:200],
                    "description": None,
                    "due_at_local": target.strftime("%Y-%m-%dT%H:%M:%S"),
                    "reminder_at_local": target.strftime("%Y-%m-%dT%H:%M:%S"),
                    "priority": "medium",
                    "project": None,
                    "tags": [],
                    "confidence": 0.95,
                    "requires_confirmation": False,
                }
            ]
        if "запомни" in lowered:
            memory_text = re.sub(r"запомни[:,]?\s*", "", message, flags=re.IGNORECASE).strip()
            result["intents"] = [*result["intents"], "store_memory"]
            result["memory_candidates"] = [
                {
                    "kind": "preference",
                    "text": memory_text or message,
                    "importance": 4,
                    "confidence": 0.95,
                    "requires_confirmation": False,
                }
            ]
        return result
