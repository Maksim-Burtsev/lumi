"""Backend-only chat language QA.

Run with the backend DB available:
    python -m lumi.scripts.chat_language_qa --out output/language-qa

The script uses the real AssistantOrchestrator, DB models, tool execution, and
LLM call logging, but swaps the external model for a deterministic provider so
the language cases are stable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from lumi.assistant.orchestrator import AssistantOrchestrator
from lumi.db.models import AgentRun, LLMCall, Message, MessageRole, Task, ToolCall
from lumi.db.session import dispose_engine, session_scope
from lumi.llm.base import LLMMessage, LLMResponse, content_char_count, content_to_text
from lumi.llm.gateway import LLMGateway
from lumi.services.users import UserService

QA_TELEGRAM_ID = 990000777


@dataclass(frozen=True)
class ChatCase:
    slug: str
    language: str
    user_message: str
    expected_reply_marker: str
    expected_progress: str | None
    expected_tool: str | None


CHAT_CASES = [
    ChatCase(
        slug="en_task",
        language="en",
        user_message="Add task verify English-only UI QA",
        expected_reply_marker="Done",
        expected_progress="Creating task...",
        expected_tool="create_task",
    ),
    ChatCase(
        slug="ru_task",
        language="ru",
        user_message="Добавь задачу проверить английский интерфейс",
        expected_reply_marker="Готово",
        expected_progress="Making changes...",
        expected_tool="create_task",
    ),
    ChatCase(
        slug="it_task",
        language="it",
        user_message="Aggiungi task controllare interfaccia inglese",
        expected_reply_marker="Fatto",
        expected_progress="Making changes...",
        expected_tool="create_task",
    ),
    ChatCase(
        slug="es_task",
        language="es",
        user_message="Agrega tarea validar interfaz en ingles",
        expected_reply_marker="Listo",
        expected_progress="Making changes...",
        expected_tool="create_task",
    ),
    ChatCase(
        slug="ru_language_request",
        language="ru",
        user_message="Сделай интерфейс на русском и всегда отвечай по-русски",
        expected_reply_marker="Интерфейс Mini App только на английском",
        expected_progress=None,
        expected_tool=None,
    ),
]


def _extract_message(prompt: str) -> str:
    match = re.search(r"\nMessage:\s*(.*?)\nLoop step:", prompt, flags=re.S)
    if match:
        return match.group(1).strip()
    return prompt.strip()


def _language_for_message(message: str) -> str:
    lowered = message.lower()
    if re.search(r"[а-яё]", lowered):
        return "ru"
    if any(token in lowered for token in ("aggiungi", "interfaccia", "controllare")):
        return "it"
    if any(token in lowered for token in ("agrega", "validar", "ingles")):
        return "es"
    return "en"


def _title_from_message(message: str, language: str) -> str:
    patterns = {
        "en": r"add task\s+(.+)",
        "ru": r"добавь задачу\s+(.+)",
        "it": r"aggiungi task\s+(.+)",
        "es": r"agrega tarea\s+(.+)",
    }
    match = re.search(patterns.get(language, patterns["en"]), message, flags=re.I)
    return (match.group(1).strip() if match else message).strip(" .")


def _english_progress_for_language(language: str) -> tuple[str, str]:
    if language == "en":
        return "Creating task...", "writing"
    raw_statuses = {
        "ru": "Создаю задачу...",
        "it": "Creo la task...",
        "es": "Creando tarea...",
    }
    return raw_statuses.get(language, "Working on it..."), "writing"


class LanguageQaProvider:
    name = "language-qa"
    model = "language-qa-1"

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
        joined = "\n".join(content_to_text(message.content) for message in messages)
        if request_kind == "action_reply_renderer":
            return self._render_action_reply(joined)
        if request_kind == "agent_planner":
            return self._plan(_extract_message(joined))
        return {
            "mode": "final_answer",
            "language": "en",
            "tool_calls": [],
            "final_answer": "OK",
            "should_answer_normally": True,
        }

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
        text = "OK"
        input_chars = sum(content_char_count(message.content) for message in messages) + len(system or "")
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            latency_ms=1,
            input_chars=input_chars,
            output_chars=len(text),
            input_tokens=max(1, input_chars // 4),
            output_tokens=max(1, len(text) // 4),
        )

    def _plan(self, message: str) -> dict[str, Any]:
        language = _language_for_message(message)
        lowered = message.lower()
        language_request = (
            "сделай интерфейс" in lowered
            or "смени интерфейс" in lowered
            or "язык" in lowered
            or "always answer" in lowered
            or "reply language" in lowered
        )
        if language_request:
            answer = {
                "ru": "Интерфейс Mini App только на английском. Ответы уже совпадают с языком каждого сообщения.",
                "it": "L'interfaccia Mini App e solo in inglese. Le risposte seguono gia la lingua di ogni messaggio.",
                "es": "La interfaz de Mini App solo esta en ingles. Las respuestas ya siguen el idioma de cada mensaje.",
            }.get(
                language,
                "The Mini App UI is English only. Replies already match each message.",
            )
            return {
                "mode": "final_answer",
                "language": language,
                "tool_calls": [],
                "final_answer": answer,
                "should_answer_normally": True,
            }
        raw_status, progress_kind = _english_progress_for_language(language)
        return {
            "mode": "tool_calls",
            "language": language,
            "user_visible_status": raw_status,
            "progress_kind": progress_kind,
            "tool_calls": [
                {
                    "name": "create_task",
                    "args": {
                        "title": _title_from_message(message, language),
                        "priority": "medium",
                        "confidence": 0.95,
                        "requires_confirmation": False,
                    },
                    "confidence": 0.95,
                    "requires_confirmation": False,
                    "evidence": ["language qa case"],
                }
            ],
            "should_answer_normally": False,
        }

    @staticmethod
    def _render_action_reply(prompt: str) -> dict[str, Any]:
        marker = "payload_json:"
        payload_text = prompt.split(marker, 1)[-1].strip() if marker in prompt else "{}"
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            payload = {}
        language = str(payload.get("target_language") or "en") if isinstance(payload, dict) else "en"
        messages = {
            "en": "Done, I added the task.",
            "ru": "Готово, добавил задачу.",
            "it": "Fatto, ho aggiunto la task.",
            "es": "Listo, agregue la tarea.",
        }
        return {"message": messages.get(language, messages["en"]), "button_labels": {}}


def _markdown_escape(value: object) -> str:
    text = str(value).replace("\n", "<br>")
    return text.replace("|", "\\|")


def _progress_is_english(progress: list[str]) -> bool:
    return all(update == "__thinking__" or all(ord(char) < 128 for char in update) for update in progress)


async def _prepare_user() -> None:
    async with session_scope() as session:
        user = await UserService(session).ensure_user(
            QA_TELEGRAM_ID,
            telegram_chat_id=QA_TELEGRAM_ID,
            first_name="Language QA",
            language_code="ru",
        )
        user.locale = "ru"
        user.settings = {
            "locale_source": "manual",
            "reply_language_mode": "fixed",
            "reply_language": "it",
            "time_format": "24h",
            "theme_mode": "telegram",
        }


async def _run_case(case: ChatCase, gateway: LLMGateway) -> dict[str, Any]:
    progress: list[str] = []

    async def on_progress(stage: str) -> None:
        progress.append(stage)

    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=gateway)
        result = await orchestrator.handle_user_message(
            telegram_user_id=QA_TELEGRAM_ID,
            telegram_chat_id=QA_TELEGRAM_ID,
            telegram_message_id=None,
            text=case.user_message,
            first_name="Language QA",
            on_progress=on_progress,
        )
        run = await session.get(AgentRun, result.agent_run_id)
        user = await UserService(session).get_by_telegram_id(QA_TELEGRAM_ID)
        if user is None:
            raise RuntimeError("QA user was not created")
        tool_rows = (
            await session.execute(
                select(ToolCall).where(ToolCall.agent_run_id == result.agent_run_id).order_by(ToolCall.created_at)
            )
        ).scalars().all()
        llm_rows = (
            await session.execute(
                select(LLMCall).where(LLMCall.agent_run_id == result.agent_run_id).order_by(LLMCall.created_at)
            )
        ).scalars().all()
        assistant_message = (
            await session.execute(
                select(Message)
                .where(
                    Message.user_id == user.id,
                    Message.role == MessageRole.ASSISTANT,
                    Message.content == result.reply_text,
                )
                .order_by(Message.created_at.desc())
            )
        ).scalars().first()
        created_task = None
        if case.expected_tool == "create_task":
            created_task = (
                await session.execute(
                    select(Task)
                    .where(Task.user_id == user.id)
                    .order_by(Task.created_at.desc())
                    .limit(1)
                )
            ).scalars().first()

        tool_names = [row.tool_name for row in tool_rows]
        checks = {
            "reply_marker": case.expected_reply_marker in result.reply_text,
            "progress": case.expected_progress is None or case.expected_progress in progress,
            "progress_english": _progress_is_english(progress),
            "tool_policy": (
                (case.expected_tool in tool_names)
                if case.expected_tool
                else "set_language" not in tool_names and not tool_names
            ),
            "user_locale": bool(user and user.locale == "en"),
            "settings": bool(
                user
                and user.settings.get("reply_language_mode") == "auto"
                and user.settings.get("reply_language") == "en"
            ),
            "llm_logs": len(llm_rows) >= 1,
            "message_saved": assistant_message is not None,
            "task_created": case.expected_tool != "create_task" or created_task is not None,
        }
        verdict = "OK" if all(checks.values()) else "FAIL"
        return {
            "case": case.slug,
            "language": case.language,
            "user_message": case.user_message,
            "progress": progress,
            "reply": result.reply_text,
            "tool_calls": [{"tool": row.tool_name, "status": row.status} for row in tool_rows],
            "llm_calls": [{"kind": row.request_kind, "status": row.status} for row in llm_rows],
            "agent_run_id": str(result.agent_run_id),
            "result_summary": run.result_summary if run else None,
            "created_task": created_task.title if created_task else None,
            "checks": checks,
            "verdict": verdict,
        }


def _write_report(out_dir: Path, rows: list[dict[str, Any]]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "chat-language-qa.json"
    md_path = out_dir / "chat-language-qa.md"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    generated_at = datetime.now(UTC).isoformat()
    lines = [
        "# Chat Language QA",
        "",
        f"Generated: {generated_at}",
        "",
        "| Case | User message | Progress | Reply | Tool calls | LLM calls | Verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        tool_calls = ", ".join(f"{item['tool']}:{item['status']}" for item in row["tool_calls"]) or "-"
        llm_calls = ", ".join(f"{item['kind']}:{item['status']}" for item in row["llm_calls"]) or "-"
        lines.append(
            "| "
            + " | ".join(
                _markdown_escape(value)
                for value in (
                    row["case"],
                    row["user_message"],
                    ", ".join(row["progress"]) or "-",
                    row["reply"],
                    tool_calls,
                    llm_calls,
                    row["verdict"],
                )
            )
            + " |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


async def run(out_dir: Path) -> int:
    await _prepare_user()
    gateway = LLMGateway(LanguageQaProvider())
    rows = []
    for case in CHAT_CASES:
        rows.append(await _run_case(case, gateway))
    md_path, json_path = _write_report(out_dir, rows)
    await dispose_engine()
    print(f"chat language QA report: {md_path}")
    print(f"chat language QA json: {json_path}")
    return 0 if all(row["verdict"] == "OK" for row in rows) else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output/language-qa", help="report output directory")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(Path(args.out))))


if __name__ == "__main__":
    main()
