from __future__ import annotations

from lumi.dev.qa_required import required_checks_for_paths


def test_frontend_changes_do_not_trigger_assistant_regression():
    checks = required_checks_for_paths(["frontend/src/routes/TasksPage.tsx"])
    commands = {check.command for check in checks}
    assert "make frontend-build" in commands
    assert not any("assistant-core" in command for command in commands)
    assert not any("minimax-planner-smoke" in command for command in commands)


def test_tool_catalog_changes_trigger_core_and_minimax_checks():
    checks = required_checks_for_paths(["backend/src/lumi/assistant/tool_registry.py"])
    commands = {check.command for check in checks}
    assert "make assistant-core" in commands
    assert "make minimax-planner-smoke" in commands
    assert "make assistant-eval-coverage" not in commands


def test_task_service_change_triggers_task_subset_only():
    checks = required_checks_for_paths(["backend/src/lumi/services/tasks.py"])
    commands = {check.command for check in checks}
    assert "make assistant-core-task" in commands
    assert "make minimax-planner-smoke" not in commands
