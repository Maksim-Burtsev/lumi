"""Select validation commands from changed files.

The selector is intentionally static and conservative. Codex can run it before
finalizing a branch, then execute the printed commands instead of guessing which
assistant regression suites apply.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RequiredCheck:
    command: str
    when: str
    reason: str


def required_checks_for_paths(paths: list[str]) -> list[RequiredCheck]:
    normalized = sorted({path.strip() for path in paths if path.strip()})
    checks: list[RequiredCheck] = []

    def add(command: str, when: str, reason: str) -> None:
        if command == "make assistant-core":
            checks[:] = [check for check in checks if check.command != "make assistant-eval-coverage"]
        if command == "make assistant-eval-coverage" and any(
            check.command == "make assistant-core" for check in checks
        ):
            return
        if any(check.command == command for check in checks):
            return
        item = RequiredCheck(command=command, when=when, reason=reason)
        checks.append(item)

    if not normalized:
        add("make lint", "no changed paths detected", "safe default for local sanity")
        return checks

    backend_paths = [p for p in normalized if p.startswith("backend/")]
    frontend_paths = [p for p in normalized if p.startswith("frontend/")]
    docs_only = all(p.startswith("docs/") or p.endswith(".md") for p in normalized)

    if docs_only:
        add("git diff --check", "docs or markdown only", "catch whitespace/patch issues")
        return checks

    if backend_paths:
        add("make lint", "backend files changed", "backend style/import gate")

    if frontend_paths:
        add("make frontend-build", "frontend files changed", "Mini App build gate")

    assistant_common = (
        "backend/src/lumi/assistant/orchestrator.py",
        "backend/src/lumi/assistant/schemas.py",
        "backend/src/lumi/assistant/context_builder.py",
    )
    planner_common = (
        "backend/src/lumi/assistant/planner.py",
        "backend/src/lumi/assistant/prompts.py",
        "backend/src/lumi/assistant/tool_registry.py",
    )

    if any(path in normalized for path in planner_common):
        add("make assistant-eval-coverage", "planner/tool catalog changed", "new tools need coverage manifest")
        add("make assistant-core", "planner/tool catalog changed", "core backend assistant flows can regress")
        add("make minimax-planner-smoke", "planner/tool catalog changed", "real MiniMax routing can regress")
    elif any(path in normalized for path in assistant_common):
        add("make assistant-core", "assistant harness changed", "core backend assistant flows can regress")

    if "backend/src/lumi/services/tasks.py" in normalized:
        add("make assistant-core-task", "task service changed", "task assistant subset can regress")
    if (
        "backend/src/lumi/services/calendar.py" in normalized
        or "backend/src/lumi/bot/schedule_messages.py" in normalized
    ):
        add("make assistant-core-calendar", "calendar/schedule code changed", "calendar assistant subset can regress")
    if "backend/src/lumi/assistant/memory_service.py" in normalized or "backend/src/lumi/services/users.py" in normalized:
        add("make assistant-core-memory", "memory/user context changed", "memory/language assistant subset can regress")
    if any(path.startswith("backend/src/lumi/llm/") for path in normalized):
        add("make minimax-planner-smoke", "LLM provider/gateway changed", "real provider JSON routing can regress")
    if any(path.startswith("backend/src/lumi/evals/") for path in normalized):
        add("make minimax-planner-smoke", "MiniMax eval code changed", "real provider smoke command should validate itself")
    if "backend/src/lumi/dev/qa_required.py" in normalized or "scripts/qa_required.py" in normalized:
        add(
            "docker compose run --rm -e LLM_PROVIDER=mock api pytest -q tests/test_qa_required.py",
            "QA selector changed",
            "selector routing should validate itself",
        )
    if "backend/src/lumi/assistant/tool_registry.py" in normalized:
        add("make assistant-eval-coverage", "tool registry changed", "new assistant tools need coverage entries")

    if any(path in normalized for path in {
        "backend/tests/assistant_cases.py",
        "backend/tests/test_assistant_core_flows.py",
    }) or any(path.startswith("backend/tests/helpers/assistant_flow.py") for path in normalized):
        add("make assistant-core", "assistant regression tests changed", "regression pack should validate itself")
    if "backend/tests/test_assistant_eval_coverage.py" in normalized:
        add("make assistant-eval-coverage", "assistant coverage test changed", "coverage guard should validate itself")
    if "backend/tests/test_qa_required.py" in normalized:
        add(
            "docker compose run --rm -e LLM_PROVIDER=mock api pytest -q tests/test_qa_required.py",
            "QA selector tests changed",
            "selector tests should validate themselves",
        )

    backend_test_paths = [p for p in normalized if p.startswith("backend/tests/")]
    if backend_test_paths and not any(check.command.startswith("make assistant") for check in checks):
        add(
            "docker compose run --rm -e LLM_PROVIDER=mock api pytest -q tests",
            "backend tests changed",
            "changed test suite should still run in app container",
        )

    if not checks:
        add("git diff --check", "non-runtime files changed", "catch whitespace/patch issues")
    return checks


def changed_paths(base: str) -> list[str]:
    commands = [
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    paths: set[str] = set()
    for command in commands:
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True)
        except FileNotFoundError:
            continue
        if result.returncode == 0:
            paths.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(paths)


def render_table(checks: list[RequiredCheck]) -> str:
    if not checks:
        return "No checks required."
    rows = [("Command", "When", "Reason")]
    rows.extend((check.command, check.when, check.reason) for check in checks)
    widths = [max(len(row[index]) for row in rows) for index in range(3)]
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
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)

    paths = args.paths or changed_paths(args.base)
    checks = required_checks_for_paths(paths)
    if args.json:
        print(json.dumps([asdict(check) for check in checks], ensure_ascii=False, indent=2))
    else:
        print(render_table(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
