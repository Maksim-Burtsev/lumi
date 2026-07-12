from __future__ import annotations

import pytest

from lumi.dev.qa_required import required_checks_for_paths


def test_frontend_changes_do_not_trigger_assistant_regression():
    checks = required_checks_for_paths(["frontend/src/routes/TasksPage.tsx"])
    commands = {check.command for check in checks}
    assert commands == {"make frontend-check"}
    assert not any("assistant-core" in command for command in commands)
    assert not any("minimax-planner-smoke" in command for command in commands)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("backend/src/lumi/api/routes/focus.py", "make focus-check"),
        ("backend/src/lumi/services/focus.py", "make focus-check"),
        ("backend/tests/test_focus_api.py", "make focus-check"),
        ("backend/src/lumi/api/routes/projects.py", "make tasks-check"),
        ("backend/src/lumi/services/assistant_suggestions.py", "make tasks-check"),
        ("backend/src/lumi/services/tasks.py", "make tasks-check"),
        ("backend/src/lumi/api/routes/today.py", "make planning-check"),
        ("backend/src/lumi/services/calendar.py", "make planning-check"),
        ("backend/src/lumi/services/work_blocks.py", "make planning-check"),
        ("backend/src/lumi/security/csrf.py", "make auth-check"),
        ("backend/src/lumi/security/web_session.py", "make auth-check"),
        ("backend/src/lumi/api/routes/auth.py", "make auth-check"),
        ("backend/src/lumi/services/focus_analysis.py", "make analytics-check"),
        ("backend/src/lumi/services/reflection_analysis.py", "make analytics-check"),
        ("backend/alembic/versions/123_focus_session_analyses.py", "make analytics-check"),
    ],
)
def test_product_v2_paths_trigger_domain_checks(path, expected):
    commands = [check.command for check in required_checks_for_paths([path])]
    assert expected in commands
    assert commands.count(expected) == 1


@pytest.mark.parametrize(
    "path",
    [
        "backend/src/lumi/api/serializers.py",
        "backend/src/lumi/db/models.py",
        "backend/alembic/versions/123_product_v2.py",
    ],
)
def test_shared_product_contract_paths_trigger_all_domain_checks(path):
    commands = {check.command for check in required_checks_for_paths([path])}
    assert {
        "make focus-check",
        "make tasks-check",
        "make planning-check",
        "make auth-check",
        "make analytics-check",
    } <= commands


def test_repeated_domain_paths_are_deduplicated():
    checks = required_checks_for_paths(
        [
            "backend/src/lumi/api/routes/focus.py",
            "backend/src/lumi/services/focus.py",
            "backend/tests/test_focus_api.py",
        ]
    )
    commands = [check.command for check in checks]
    assert commands.count("make focus-check") == 1


def test_tool_catalog_changes_trigger_core_and_minimax_checks():
    checks = required_checks_for_paths(["backend/src/lumi/assistant/tool_registry.py"])
    commands = {check.command for check in checks}
    assert "make assistant-core" in commands
    assert "make minimax-planner-smoke" in commands
    assert "make assistant-eval-coverage" not in commands


def test_task_service_change_triggers_task_subset_only():
    checks = required_checks_for_paths(["backend/src/lumi/services/tasks.py"])
    commands = {check.command for check in checks}
    assert "make tasks-check" in commands
    assert "make assistant-core-task" in commands
    assert "make minimax-planner-smoke" not in commands


def test_unknown_backend_test_keeps_full_suite_fallback():
    checks = required_checks_for_paths(["backend/tests/test_new_domain.py"])
    commands = {check.command for check in checks}
    assert "docker compose run --rm -e LLM_PROVIDER=mock api pytest -q tests" in commands
