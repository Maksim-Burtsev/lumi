"""Scripted chat-like QA for MiniMax agent tool surface.

Run:
  python -m lumi.scripts.agent_chat_qa --scenario-set p0_p1 --json output/agent-chat-qa/results.json

The script uses the real AssistantOrchestrator/tool execution path with a
deterministic planner provider. That keeps DB/tool assertions stable; use real
Telegram QA separately for MiniMax wording/routing spot checks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from lumi.assistant.memory_service import MemoryService
from lumi.assistant.orchestrator import AssistantOrchestrator
from lumi.config import get_settings
from lumi.db.models import (
    CalendarEvent,
    CalendarEventStatus,
    CalendarSource,
    Connector,
    ConnectorStatus,
    ConnectorType,
    Memory,
    MemoryKind,
    ToolCall,
)
from lumi.db.session import dispose_engine, session_scope
from lumi.llm.base import LLMResponse, content_to_text
from lumi.llm.gateway import LLMGateway, reset_llm_provider
from lumi.services.calendar import CalendarService
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.utils.time import local_to_utc, utc_now, utc_to_local


@dataclass(slots=True)
class ScenarioResult:
    index: int
    user_message: str
    expected: str
    bot_reply: str
    evidence: str
    ok: bool
    progress_statuses: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class ScriptedPlannerProvider:
    name = "scripted-agent-qa"
    model = "scripted-agent-qa-1"

    def __init__(self, plan: dict[str, Any]) -> None:
        self.plan = plan
        self.used = False

    async def complete_json(self, **kwargs) -> dict:
        request_kind = kwargs["request_kind"]
        if request_kind == "agent_planner":
            if self.used:
                return {
                    "mode": "final_answer",
                    "final_answer": "Done.",
                    "tool_calls": [],
                    "should_answer_normally": False,
                    "language": self.plan.get("language") or "ru",
                }
            self.used = True
            return self.plan
        if request_kind == "action_reply_renderer":
            prompt = (kwargs.get("system") or "") + "\n" + content_to_text((kwargs.get("messages") or [])[-1].content)
            payload = _renderer_payload(prompt)
            outcomes = payload.get("action_outcomes") or []
            lines = [
                str(outcome.get("fallback_text") or "").strip()
                for outcome in outcomes
                if isinstance(outcome, dict) and str(outcome.get("fallback_text") or "").strip()
            ]
            return {"message": "\n".join(lines) if lines else "Done.", "button_labels": {}}
        raise AssertionError(f"unexpected request_kind: {request_kind}")

    async def complete(self, **kwargs) -> LLMResponse:
        return LLMResponse(
            text="Done.",
            provider=self.name,
            model=self.model,
            latency_ms=1,
            input_chars=1,
            output_chars=5,
        )


def _renderer_payload(prompt: str) -> dict[str, Any]:
    marker = "payload_json:"
    if marker not in prompt:
        return {}
    try:
        return json.loads(prompt.split(marker, 1)[1].strip())
    except json.JSONDecodeError:
        return {}


def _plan(tool_calls: list[dict[str, Any]], *, language: str = "ru") -> dict[str, Any]:
    return {
        "mode": "tool_calls",
        "tool_calls": tool_calls,
        "should_answer_normally": False,
        "language": language,
        "user_visible_status": "Разбираю запрос…",
        "progress_kind": "resolving",
    }


def _tool(name: str, args: dict[str, Any], *, confidence: float = 0.96) -> dict[str, Any]:
    return {
        "name": name,
        "args": args,
        "confidence": confidence,
        "requires_confirmation": False,
        "source": "text",
        "evidence": ["scripted QA"],
    }


def _local_dt(day, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour=hour, minute=minute))


async def _run_chat(
    *,
    telegram_user_id: int,
    message_id: int,
    text: str,
    plan: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], list[str], str]:
    statuses: list[str] = []

    async def on_progress(status: str) -> None:
        statuses.append(status)

    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(ScriptedPlannerProvider(plan)))
        result = await orchestrator.handle_user_message(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_user_id,
            telegram_message_id=message_id,
            text=text,
            first_name="Agent QA",
            on_progress=on_progress,
        )
        run_id = result.agent_run_id
        calls: list[dict[str, Any]] = []
        if run_id is not None:
            rows = await session.execute(
                select(ToolCall).where(ToolCall.agent_run_id == run_id).order_by(ToolCall.created_at)
            )
            for call in rows.scalars():
                calls.append({
                    "tool_name": call.tool_name,
                    "status": call.status,
                    "args": call.args_json,
                    "result": call.result_json,
                })
        return result.reply_text, calls, statuses, str(run_id) if run_id else ""


def _calls_evidence(calls: list[dict[str, Any]]) -> str:
    parts = []
    for call in calls:
        result = call.get("result") or {}
        entity = result.get("task_id") or result.get("event_id") or result.get("job_id")
        suffix = f" {entity}" if entity else ""
        parts.append(f"{call['tool_name']}:{call['status']}{suffix}")
    return "; ".join(parts) or "no tool calls"


async def _qa_user(telegram_user_id: int):
    async with session_scope() as session:
        user = await UserService(session).ensure_user(telegram_user_id, first_name="Agent QA")
        await UserService(session).ensure_main_conversation(user)
        return user.id


async def _seed_block(telegram_user_id: int, *, title: str, day, start_hour: int, end_hour: int) -> str:
    async with session_scope() as session:
        user = await UserService(session).ensure_user(telegram_user_id)
        event = await CalendarService(session).create_internal_block(
            user,
            title=title,
            start_at=local_to_utc(_local_dt(day, start_hour), user.timezone),
            end_at=local_to_utc(_local_dt(day, end_hour), user.timezone),
            created_by="agent",
            metadata={"agent_chat_qa": True},
        )
        return str(event.id)


async def _seed_task(telegram_user_id: int, *, title: str, day, due_hour: int) -> str:
    async with session_scope() as session:
        user = await UserService(session).ensure_user(telegram_user_id)
        task = await TaskService(session).create_task(
            user,
            title=title,
            due_at=local_to_utc(_local_dt(day, due_hour), user.timezone),
            actor="agent",
            created_by="agent",
        )
        return str(task.id)


async def _free_day_for_qa(telegram_user_id: int):
    async with session_scope() as session:
        user = await UserService(session).ensure_user(telegram_user_id)
        today = utc_to_local(utc_now(), user.timezone).date()
        calendar = CalendarService(session)
        for offset in range(1, 45):
            candidate = today + timedelta(days=offset)
            start = local_to_utc(_local_dt(candidate, 16), user.timezone)
            end = local_to_utc(_local_dt(candidate, 19), user.timezone)
            events = await calendar.list_events(user, start, end)
            if not events:
                return candidate
        return today + timedelta(days=60)


async def _event_window(telegram_user_id: int, event_id: str) -> str:
    async with session_scope() as session:
        user = await UserService(session).ensure_user(telegram_user_id)
        event = await CalendarService(session).get_event(user, uuid.UUID(event_id))
        if event is None:
            return "missing"
        return (
            f"{event.title} "
            f"{utc_to_local(event.start_at, user.timezone).strftime('%H:%M')}-"
            f"{utc_to_local(event.end_at, user.timezone).strftime('%H:%M')} "
            f"{event.status.value}"
        )


async def _event_id_by_title(telegram_user_id: int, title: str) -> str:
    async with session_scope() as session:
        user = await UserService(session).ensure_user(telegram_user_id)
        result = await session.execute(
            select(CalendarEvent)
            .where(CalendarEvent.user_id == user.id, CalendarEvent.title == title)
            .order_by(CalendarEvent.created_at.desc())
            .limit(1)
        )
        event = result.scalar_one()
        return str(event.id)


async def _task_due(telegram_user_id: int, task_id: str) -> str:
    async with session_scope() as session:
        user = await UserService(session).ensure_user(telegram_user_id)
        task = await TaskService(session).get(user, uuid.UUID(task_id))
        if task is None or task.due_at is None:
            return "missing"
        return f"{task.title} {utc_to_local(task.due_at, user.timezone).strftime('%H:%M')} {task.status.value}"


async def run_p0_p1(telegram_user_id: int) -> list[ScenarioResult]:
    await _qa_user(telegram_user_id)
    reset_llm_provider()
    suffix = utc_now().strftime("%H%M%S")
    results: list[ScenarioResult] = []
    message_id = 7000

    day = await _free_day_for_qa(telegram_user_id)

    async def record(user_message: str, expected: str, plan: dict[str, Any], check) -> None:
        nonlocal message_id
        message_id += 1
        reply, calls, statuses, _run_id = await _run_chat(
            telegram_user_id=telegram_user_id,
            message_id=message_id,
            text=user_message,
            plan=plan,
        )
        ok, extra = await check(reply, calls)
        results.append(ScenarioResult(
            index=len(results) + 1,
            user_message=user_message,
            expected=expected,
            bot_reply=reply,
            evidence=extra or _calls_evidence(calls),
            ok=ok,
            progress_statuses=statuses,
            tool_calls=calls,
        ))

    hair_title = f"Стрижка QA {suffix}"
    dalma_title = f"Dalma QA {suffix}"
    await record(
        f"поставь завтра блок 16-17 «{hair_title}» и потом блок 17-18 «{dalma_title}»",
        "create_internal_calendar_block x2",
        _plan([
            _tool("create_internal_calendar_block", {
                "title": hair_title,
                "start_at_local": _local_dt(day, 16).isoformat(),
                "end_at_local": _local_dt(day, 17).isoformat(),
            }),
            _tool("create_internal_calendar_block", {
                "title": dalma_title,
                "start_at_local": _local_dt(day, 17).isoformat(),
                "end_at_local": _local_dt(day, 18).isoformat(),
            }),
        ]),
        lambda _reply, calls: _async_check(
            sum(1 for call in calls if call["tool_name"] == "create_internal_calendar_block" and call["status"] == "completed") == 2,
            _calls_evidence(calls),
        ),
    )
    dalma_event_id = await _event_id_by_title(telegram_user_id, dalma_title)
    await record(
        f"перенеси {dalma_title} на полчаса",
        "update_calendar_event shift_minutes=30",
        _plan([_tool("update_calendar_event", {"event_query": dalma_title, "shift_minutes": 30})]),
        lambda _reply, calls: _check_event_window(
            telegram_user_id, dalma_event_id, "17:30-18:30", calls
        ),
    )

    ambiguous_title = f"Dalma Ambig QA {suffix}"
    ambiguous_task_id = await _seed_task(telegram_user_id, title=ambiguous_title, day=day, due_hour=15)
    await _seed_block(
        telegram_user_id, title=ambiguous_title, day=day, start_hour=17, end_hour=18
    )
    await record(
        f"перенеси {ambiguous_title} на 17:30",
        "resolve_entity -> choice, no write",
        _plan([_tool("resolve_entity", {"query": ambiguous_title, "domains": ["tasks", "calendar"]})]),
        lambda reply, calls: _async_check(
            any(call["tool_name"] == "resolve_entity" and call["status"] == "requires_confirmation" for call in calls)
            and "Что именно" in reply,
            _calls_evidence(calls),
        ),
    )
    await record(
        f"перенеси задачу {ambiguous_title} на 21:00",
        "update_task due_time_local",
        _plan([_tool("update_task", {"task_query": ambiguous_title, "updates": {"due_time_local": "21:00"}})]),
        lambda _reply, calls: _check_task_due(telegram_user_id, ambiguous_task_id, "21:00", calls),
    )
    await record(
        f"убери блок {dalma_title}",
        "cancel_calendar_event",
        _plan([_tool("cancel_calendar_event", {"event_query": dalma_title})]),
        lambda _reply, calls: _check_event_window(
            telegram_user_id, dalma_event_id, "cancelled", calls
        ),
    )

    external_title = f"External QA {suffix}"
    async with session_scope() as session:
        user = await UserService(session).ensure_user(telegram_user_id)
        external = CalendarEvent(
            user_id=user.id,
            source=CalendarSource.GOOGLE,
            external_calendar_id="primary",
            external_event_id=f"ext-{suffix}",
            title=external_title,
            start_at=local_to_utc(_local_dt(day, 18), user.timezone),
            end_at=local_to_utc(_local_dt(day, 19), user.timezone),
            timezone=user.timezone,
            status=CalendarEventStatus.CONFIRMED,
            created_by="external_sync",
        )
        session.add(external)
        await session.flush()
        external_id = str(external.id)
    await record(
        f"перенеси {external_title} на 19:30",
        "external update unsupported",
        _plan([_tool("update_calendar_event", {"event_query": external_title, "start_time_local": "19:30"})]),
        lambda _reply, calls: _check_event_window(
            telegram_user_id, external_id, "18:00-19:00", calls, expect_tool_status="skipped"
        ),
    )

    async with session_scope() as session:
        user = await UserService(session).ensure_user(telegram_user_id)
        memory = Memory(
            user_id=user.id,
            kind=MemoryKind.FACT,
            text_="QA memory prefers short replies.",
            normalized_text="qa memory prefers short replies",
            importance=0.7,
            confidence=0.9,
        )
        session.add(memory)
        await session.flush()
        memory_id = str(memory.id)
    await record(
        "прочитай, обнови и удали QA memory",
        "read_memories -> update_memory -> delete_memory",
        _plan([
            _tool("read_memories", {"query": "QA memory"}),
            _tool("update_memory", {"memory_id": memory_id, "text": "QA memory prefers concise replies."}),
            _tool("delete_memory", {"memory_id": memory_id}),
        ]),
        lambda _reply, calls: _check_memory_deleted(telegram_user_id, memory_id, calls),
    )

    async with session_scope() as session:
        user = await UserService(session).ensure_user(telegram_user_id)
        existing = await session.execute(
            select(Connector).where(Connector.user_id == user.id, Connector.type == ConnectorType.GOOGLE)
        )
        connector = existing.scalar_one_or_none()
        if connector is None:
            connector = Connector(
                user_id=user.id,
                type=ConnectorType.GOOGLE,
            )
            session.add(connector)
        connector.status = ConnectorStatus.CONNECTED
        connector.scopes = ["calendar.readonly"]
    await record(
        "покажи settings/connectors и поставь time format 24h",
        "read_settings -> update_settings -> read_connectors",
        _plan([
            _tool("read_settings", {}),
            _tool("update_settings", {"time_format": "24h"}),
            _tool("read_connectors", {}),
        ]),
        lambda _reply, calls: _check_settings_updated(telegram_user_id, calls),
    )

    return results


async def _async_check(ok: bool, evidence: str) -> tuple[bool, str]:
    return ok, evidence


async def _check_event_window(
    telegram_user_id: int,
    event_id: str,
    expected: str,
    calls: list[dict[str, Any]],
    *,
    expect_tool_status: str | None = None,
) -> tuple[bool, str]:
    window = await _event_window(telegram_user_id, event_id)
    status_ok = True
    if expect_tool_status:
        status_ok = any(call["status"] == expect_tool_status for call in calls)
    return expected in window and status_ok, f"{window}; {_calls_evidence(calls)}"


async def _check_task_due(
    telegram_user_id: int,
    task_id: str,
    expected: str,
    calls: list[dict[str, Any]],
) -> tuple[bool, str]:
    due = await _task_due(telegram_user_id, task_id)
    return expected in due, f"{due}; {_calls_evidence(calls)}"


async def _check_memory_deleted(
    telegram_user_id: int,
    memory_id: str,
    calls: list[dict[str, Any]],
) -> tuple[bool, str]:
    async with session_scope() as session:
        user = await UserService(session).ensure_user(telegram_user_id)
        memory = await MemoryService(session).get(user, uuid.UUID(memory_id))
    return memory is None, f"memory_exists={memory is not None}; {_calls_evidence(calls)}"


async def _check_settings_updated(
    telegram_user_id: int,
    calls: list[dict[str, Any]],
) -> tuple[bool, str]:
    async with session_scope() as session:
        user = await UserService(session).ensure_user(telegram_user_id)
        time_format = (user.settings or {}).get("time_format")
    return time_format == "24h", f"time_format={time_format}; {_calls_evidence(calls)}"


def _markdown_table(results: list[ScenarioResult]) -> str:
    lines = [
        "| # | User message | Expected intent/tool | Bot reply | DB/tool evidence | Result |",
        "|---:|---|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            "| "
            + " | ".join([
                str(result.index),
                _md_cell(result.user_message),
                _md_cell(result.expected),
                _md_cell(result.bot_reply),
                _md_cell(result.evidence),
                "PASS" if result.ok else "FAIL",
            ])
            + " |"
        )
    return "\n".join(lines)


def _md_cell(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())[:500]


def _json_payload(results: list[ScenarioResult]) -> dict[str, Any]:
    return {
        "results": [
            {
                "index": item.index,
                "user_message": item.user_message,
                "expected": item.expected,
                "bot_reply": item.bot_reply,
                "evidence": item.evidence,
                "ok": item.ok,
                "progress_statuses": item.progress_statuses,
                "tool_calls": item.tool_calls,
            }
            for item in results
        ],
        "pass_count": sum(1 for item in results if item.ok),
        "fail_count": sum(1 for item in results if not item.ok),
    }


def _write_json(path_raw: str, payload: dict[str, Any]) -> Path:
    path = Path(path_raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def amain(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-set", default="p0_p1", choices=["p0_p1"])
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--telegram-user-id", type=int, default=None)
    args = parser.parse_args(argv)

    settings = get_settings()
    telegram_user_id = (
        args.telegram_user_id
        or (settings.allowed_telegram_user_ids[0] if settings.allowed_telegram_user_ids else 990000002)
    )
    results = await run_p0_p1(telegram_user_id)
    table = _markdown_table(results)
    print(table)
    payload = _json_payload(results)
    if args.json_path:
        path = await asyncio.to_thread(_write_json, args.json_path, payload)
        print(f"\nJSON saved: {path}")
    await dispose_engine()
    return 0 if all(item.ok for item in results) else 1


def main() -> None:
    sys.exit(asyncio.run(amain()))


if __name__ == "__main__":
    main()
