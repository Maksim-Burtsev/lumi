"""Real MiniMax planner-routing smoke tests.

This command validates whether the live model still maps canonical user
messages to the expected planner mode/tool/argument shape. It does not execute
backend tools and does not require Telegram, Mini App, or a database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from lumi.assistant.planner import AgentPlanner
from lumi.config import get_settings
from lumi.db.models import User
from lumi.llm.base import LLMMessage
from lumi.llm.minimax import MiniMaxProvider


@dataclass(frozen=True)
class PlannerSmokeCase:
    id: str
    message: str
    expected_mode: str
    expected_tool: str | None = None
    expected_args: dict[str, Any] = field(default_factory=dict)
    known_context: str | None = None


@dataclass
class PlannerSmokeResult:
    id: str
    ok: bool
    elapsed_ms: int
    mode: str | None
    tool_names: list[str]
    failures: list[str]


class DirectPlannerGateway:
    def __init__(self, provider: MiniMaxProvider) -> None:
        self.provider = provider

    async def complete_json(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        json_schema_hint: dict[str, Any] | None = None,
        request_kind: str,
        user_id: uuid.UUID | None = None,
        agent_run_id: uuid.UUID | None = None,
        session=None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        return await self.provider.complete_json(
            messages=messages,
            system=system,
            json_schema_hint=json_schema_hint,
            request_kind=request_kind,
            temperature=temperature,
            max_tokens=max_tokens,
        )


CASES: tuple[PlannerSmokeCase, ...] = (
    PlannerSmokeCase(
        id="task_create_project_ru",
        message="Добавь в проект Lumi задачу написать regression pack",
        expected_mode="tool_calls",
        expected_tool="create_task",
        expected_args={"project": "Lumi"},
    ),
    PlannerSmokeCase(
        id="task_project_followup_ru",
        message="И в тот же проект добавь подготовить отчет по тестам",
        expected_mode="tool_calls",
        expected_tool="create_task",
        expected_args={"project_ref": "last_task_project"},
        known_context="Recent task action: created task in project Lumi. last_task_project=Lumi.",
    ),
    PlannerSmokeCase(
        id="task_bulk_update_ru",
        message="Все задачи про Lumi из Работа перенеси в Lumi",
        expected_mode="tool_calls",
        expected_tool="bulk_update_tasks",
        expected_args={"from_project": "Работа"},
    ),
    PlannerSmokeCase(
        id="calendar_read_tomorrow_ru",
        message="Какие встречи завтра в календаре?",
        expected_mode="tool_calls",
        expected_tool="read_calendar_events",
    ),
    PlannerSmokeCase(
        id="calendar_move_block_ru",
        message="Перенеси блок Dalma на полчаса",
        expected_mode="tool_calls",
        expected_tool="update_calendar_event",
        expected_args={"shift_minutes": 30},
    ),
    PlannerSmokeCase(
        id="memory_store_ru",
        message="Запомни, что я люблю короткие ответы без воды",
        expected_mode="tool_calls",
        expected_tool="store_memory",
    ),
    PlannerSmokeCase(
        id="settings_language_no_tool_ru",
        message="Всегда отвечай мне на русском",
        expected_mode="final_answer",
    ),
    PlannerSmokeCase(
        id="ordinary_capabilities_no_tool_en",
        message="What can you do?",
        expected_mode="final_answer",
    ),
)


def _fake_user() -> User:
    return User(
        id=uuid.uuid4(),
        telegram_user_id=990000002,
        telegram_chat_id=990000002,
        first_name="Eval",
        username="eval",
        timezone="Europe/Moscow",
        locale="ru",
        language_code="ru",
        is_allowed=True,
    )


async def run_case(planner: AgentPlanner, case: PlannerSmokeCase) -> PlannerSmokeResult:
    started = time.monotonic()
    plan = await planner.plan(
        user=_fake_user(),
        text=case.message,
        known_context=case.known_context,
        session=None,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    failures: list[str] = []
    if plan.mode != case.expected_mode:
        failures.append(f"mode: expected {case.expected_mode}, got {plan.mode}")
    tool_names = [call.name for call in plan.tool_calls]
    if case.expected_tool is not None and case.expected_tool not in tool_names:
        failures.append(f"tool: expected {case.expected_tool}, got {tool_names}")
    if case.expected_tool is None and tool_names:
        failures.append(f"tool: expected no tools, got {tool_names}")
    if case.expected_tool is not None and plan.tool_calls:
        matching = [call for call in plan.tool_calls if call.name == case.expected_tool]
        if matching:
            args = matching[0].args
            for key, expected_value in case.expected_args.items():
                if args.get(key) != expected_value:
                    failures.append(f"arg {key}: expected {expected_value!r}, got {args.get(key)!r}")
    return PlannerSmokeResult(
        id=case.id,
        ok=not failures,
        elapsed_ms=elapsed_ms,
        mode=plan.mode,
        tool_names=tool_names,
        failures=failures,
    )


async def run_all() -> list[PlannerSmokeResult]:
    settings = get_settings()
    if not settings.minimax_api_key:
        raise RuntimeError("MINIMAX_API_KEY is required for minimax planner smoke")
    provider = MiniMaxProvider(
        api_key=settings.minimax_api_key,
        base_url=settings.minimax_base_url,
        model=settings.minimax_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    planner = AgentPlanner(DirectPlannerGateway(provider))  # type: ignore[arg-type]
    results: list[PlannerSmokeResult] = []
    for case in CASES:
        results.append(await run_case(planner, case))
    return results


def render(results: list[PlannerSmokeResult]) -> str:
    rows = [("Case", "OK", "ms", "Mode", "Tools", "Failures")]
    rows.extend(
        (
            result.id,
            "yes" if result.ok else "no",
            str(result.elapsed_ms),
            result.mode or "",
            ",".join(result.tool_names),
            "; ".join(result.failures),
        )
        for result in results
    )
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    lines = [
        " | ".join(value.ljust(widths[index]) for index, value in enumerate(rows[0])),
        "-|-".join("-" * width for width in widths),
    ]
    lines.extend(
        " | ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in rows[1:]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    results = asyncio.run(run_all())
    if args.json:
        print(json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2))
    else:
        print(render(results))
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
