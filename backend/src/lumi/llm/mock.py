"""Deterministic mock LLM provider for tests and keyless local smoke runs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

from lumi.llm.base import LLMMessage, LLMResponse, content_char_count, content_to_text

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


def _extract_tags(text: str) -> list[str]:
    return [tag for tag in re.findall(r"#([\w-]+)", text, flags=re.UNICODE) if tag]


def _extract_project(text: str) -> str | None:
    without_quotes = re.sub(r"«.*?»", "", text)
    explicit = re.search(r"\bв\s+проекте\s+([\w-]+)", without_quotes, flags=re.IGNORECASE)
    if explicit:
        return explicit.group(1)
    if re.search(r"\bв\s+Lumi\b", without_quotes, flags=re.IGNORECASE):
        return "Lumi"
    return None


class MockLLMProvider:
    name = "mock"
    model = "mock-1"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append({"request_kind": request_kind, "messages": messages, "system": system})
        text = self._respond(request_kind, messages)
        input_chars = sum(content_char_count(m.content) for m in messages) + len(system or "")
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
        self.calls.append({"request_kind": request_kind, "messages": messages, "system": system})
        full = self._respond(request_kind, messages)
        step = max(1, len(full) // 3)
        acc = ""
        for i in range(0, len(full), step):
            acc = full[: i + step]
            if on_delta is not None:
                await on_delta(acc)
        input_chars = sum(content_char_count(m.content) for m in messages) + len(system or "")
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
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        response = await self.complete(
            messages=messages, system=system, request_kind=request_kind, metadata=metadata
        )
        return json.loads(response.text)

    # ------------------------------------------------------------------

    def _respond(self, request_kind: str, messages: list[LLMMessage]) -> str:
        joined = "\n".join(content_to_text(m.content) for m in messages)
        if request_kind == "media_understanding":
            return json.dumps(
                {
                    "summary": "На изображении виден объект или документ.",
                    "visible_text": [],
                    "entities": [],
                    "action_relevant_facts": [],
                    "instruction_like_text": [],
                    "confidence": 0.5,
                    "limitations": ["mock provider does not inspect real image pixels"],
                },
                ensure_ascii=False,
            )
        if request_kind == "focused_vision":
            return json.dumps(
                {
                    "answer": "Не удалось уверенно рассмотреть эту деталь в mock-режиме.",
                    "facts": [],
                    "visible_text": [],
                    "confidence": 0.0,
                    "limitations": ["mock provider does not inspect real image pixels"],
                },
                ensure_ascii=False,
            )
        if request_kind == "agent_planner":
            language_plan = self._language_plan(_extract_user_message(joined))
            if language_plan is not None:
                return json.dumps(language_plan, ensure_ascii=False)
            return json.dumps(self._extract_signals(joined), ensure_ascii=False)
        if request_kind == "action_reply_renderer":
            return json.dumps(
                {
                    "message": self._render_action_reply(joined),
                    "button_labels": {},
                },
                ensure_ascii=False,
            )
        if request_kind == "signal_extraction":
            return json.dumps(self._extract_signals(joined), ensure_ascii=False)
        if request_kind == "chat_turn":
            # Combined call: signals extracted from the LAST user message only.
            last_user = content_to_text(messages[-1].content) if messages else ""
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
        if request_kind == "calendar_private_note_summary":
            return json.dumps(
                {"summary": "Проверить UX заметок, summary длинных заметок и правило для chat dump."},
                ensure_ascii=False,
            )
        if request_kind == "daily_planning":
            return json.dumps(
                {
                    "summary": "Свободных окон достаточно — предлагаю один фокус-блок утром.",
                    "blocks": [],
                },
                ensure_ascii=False,
            )
        if request_kind == "task_cleanup":
            return json.dumps(self._task_cleanup(joined), ensure_ascii=False)
        if request_kind == "slot_suggestions":
            return json.dumps(self._slot_suggestions(joined), ensure_ascii=False)
        # final_chat / custom / anything else
        return "Готово, я это зафиксировал."

    def _language_plan(self, message: str) -> dict[str, Any] | None:
        lowered = message.lower()
        wants_language = any(word in lowered for word in ("language", "язык", "reply", "отвечай", "ответы"))
        if not wants_language:
            return None

        language = "en" if re.search(r"[a-zA-Z]", message) else "ru"
        answer = (
            "The Mini App UI is English only. Replies already match each message."
            if language == "en"
            else "Интерфейс Mini App только на английском. Ответы уже совпадают с языком каждого сообщения."
        )
        return {
            "mode": "final_answer",
            "language": language,
            "tool_calls": [],
            "final_answer": answer,
            "should_answer_normally": True,
        }

    @staticmethod
    def _render_action_reply(joined: str) -> str:
        marker = "payload_json:"
        payload_text = joined.split(marker, 1)[-1].strip() if marker in joined else "{}"
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return "Done."
        outcomes = payload.get("action_outcomes") if isinstance(payload, dict) else None
        if not isinstance(outcomes, list) or not outcomes:
            return "Done."
        fallbacks = [
            str(outcome.get("fallback_text"))
            for outcome in outcomes
            if isinstance(outcome, dict) and outcome.get("fallback_text")
        ]
        if not fallbacks:
            return "Done."
        if len(fallbacks) == 1:
            return fallbacks[0]
        return "Done:\n" + "\n".join(f"• {item}" for item in fallbacks)

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
        task_match = re.match(
            r"\s*(?:добавь|создай|запиши)(?:\s+в\s+бэклог)?\s+задач[ау]\s+(.+?)\s*$",
            message,
            flags=re.IGNORECASE,
        )
        if task_match:
            title = task_match.group(1).strip(" ,.")
            title = title[:1].upper() + title[1:] if title else message
            result["intents"] = ["create_task"]
            result["tasks"] = [
                {
                    "title": title[:200],
                    "description": None,
                    "due_at_local": None,
                    "reminder_at_local": None,
                    "priority": "medium",
                    "project": "Работа" if "lumi" in lowered else None,
                    "tags": [],
                    "confidence": 0.7,
                    "requires_confirmation": True,
                }
            ]
            result["should_answer_normally"] = False
        rename_match = (
            re.search(
                r"задач[ау]\s+«(.+?)»\s+переименуй(?:те)?\s+в\s+«(.+?)»",
                message,
                flags=re.IGNORECASE,
            )
            or re.search(
                r"переименуй(?:те)?\s+задач[ау]\s+«(.+?)»\s+в\s+«(.+?)»",
                message,
                flags=re.IGNORECASE,
            )
        )
        if rename_match:
            result["intents"] = ["update_task"]
            result["tasks"] = []
            result["task_updates"] = [
                {
                    "operation": "rename",
                    "current_title": rename_match.group(1).strip(),
                    "new_title": rename_match.group(2).strip(),
                    "project": _extract_project(message),
                    "tags": _extract_tags(message),
                    "confidence": 0.95,
                    "requires_confirmation": False,
                }
            ]
            result["should_answer_normally"] = False
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

    def _task_cleanup(self, joined: str) -> dict[str, Any]:
        try:
            payload = json.loads(joined)
        except json.JSONDecodeError:
            payload = {}
        tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
        decisions: list[dict[str, Any]] = []
        for task in tasks[:8]:
            if not isinstance(task, dict):
                continue
            task_id = task.get("id")
            title = str(task.get("title") or "")
            if not isinstance(task_id, str):
                continue
            if task.get("estimated_minutes") is None and task.get("estimate_source") != "skipped":
                minutes = 5 if any(word in title.lower() for word in ("почт", "email", "mail")) else 30
                decisions.append({
                    "kind": "task_estimate",
                    "task_id": task_id,
                    "estimated_minutes": minutes,
                    "confidence": "high" if minutes <= 10 else "medium",
                    "reason": "Looks like a quick operational task." if minutes <= 10 else "Small enough for one focus block.",
                })
            skips = task.get("review_skips") if isinstance(task.get("review_skips"), dict) else {}
            if task.get("due_at") is None and skips.get("due_date") is not True:
                if task.get("project") == "Backlog":
                    decisions.append({
                        "kind": "task_due_date",
                        "task_id": task_id,
                        "no_deadline": True,
                        "bucket": "Someday / Backlog",
                        "confidence": "high",
                        "reason": "Backlog items can stay open without a deadline.",
                    })
                else:
                    decisions.append({
                        "kind": "task_due_date",
                        "task_id": task_id,
                        "no_deadline": True,
                        "bucket": "Needs context",
                        "confidence": "medium",
                        "reason": "No clear deadline in the task text.",
                    })
            if task.get("project_id") is None and skips.get("project") is not True:
                decisions.append({
                    "kind": "task_project",
                    "task_id": task_id,
                    "project": task.get("project") or "Backlog",
                    "confidence": "medium",
                    "reason": "Default project until a stronger project is clear.",
                })
        return {"decisions": decisions[:20]}

    def _slot_suggestions(self, joined: str) -> dict[str, Any]:
        try:
            payload = json.loads(joined)
        except json.JSONDecodeError:
            payload = {}
        tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
        ordered = [
            task.get("id")
            for task in sorted(
                [task for task in tasks if isinstance(task, dict)],
                key=lambda item: (item.get("estimated_minutes") or 999, item.get("due_at") is None),
            )
            if isinstance(task.get("id"), str)
        ]
        return {"task_ids": ordered[:3], "reason": "Best fit for this free window."}
