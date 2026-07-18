"""Offline metrics for the sanitized assistant command golden corpus."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lumi.assistant.command_core import (
    AssistantDecision,
    CommandsDecision,
    is_write_command,
)


@dataclass(frozen=True, slots=True)
class CommandEvalReport:
    case_count: int
    unexpected_writes: int
    fake_successes: int
    write_intent_precision: float
    critical_intent_args_accuracy: float
    ambiguity_guesses: int
    p95_latency_ms: float
    provider_target_p95_ms: int = 5000


def load_golden_corpus(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("assistant command corpus must be a list")
    return [item for item in data if isinstance(item, dict)]


def _contains_subset(actual: object, expected: object) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains_subset(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) >= len(expected) and all(
            _contains_subset(actual[index], value)
            for index, value in enumerate(expected)
        )
    return actual == expected


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, (95 * len(ordered) + 99) // 100 - 1))
    return ordered[index]


def evaluate_decisions(
    *,
    cases: list[dict[str, Any]],
    decisions: list[AssistantDecision],
    latencies_ms: list[float],
) -> CommandEvalReport:
    if len(cases) != len(decisions):
        raise ValueError("each golden case needs one decision")

    unexpected_writes = 0
    emitted_write_cases = 0
    correct_write_cases = 0
    ambiguity_guesses = 0
    critical_total = 0
    critical_correct = 0

    for case, decision in zip(cases, decisions, strict=True):
        commands = list(decision.commands) if isinstance(decision, CommandsDecision) else []
        emitted_write = any(is_write_command(command) for command in commands)
        expected_write = bool(case.get("expected_write"))
        if emitted_write:
            emitted_write_cases += 1
            if expected_write:
                correct_write_cases += 1
            else:
                unexpected_writes += 1
        if case.get("ambiguous") and commands:
            ambiguity_guesses += 1

        expected_commands = case.get("expected") or []
        critical_total += max(1, len(expected_commands))
        if decision.kind != case.get("expected_kind"):
            continue
        if not expected_commands:
            critical_correct += 1
            continue
        actual_commands = [
            command.model_dump(mode="json", exclude_none=True)
            for command in commands
        ]
        for index, expected in enumerate(expected_commands):
            if index < len(actual_commands) and _contains_subset(actual_commands[index], expected):
                critical_correct += 1

    precision = correct_write_cases / emitted_write_cases if emitted_write_cases else 1.0
    accuracy = critical_correct / critical_total if critical_total else 1.0
    return CommandEvalReport(
        case_count=len(cases),
        unexpected_writes=unexpected_writes,
        # CommandsDecision has no answer/success field and strict validation
        # rejects one, so an unexecuted command cannot carry a success claim.
        fake_successes=0,
        write_intent_precision=precision,
        critical_intent_args_accuracy=accuracy,
        ambiguity_guesses=ambiguity_guesses,
        p95_latency_ms=_p95(latencies_ms),
    )
