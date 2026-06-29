from __future__ import annotations

from lumi.assistant.tool_registry import TOOL_NAMES

from .assistant_cases import ASSISTANT_CORE_CASES, ASSISTANT_TOOL_COVERAGE


def test_assistant_tool_registry_has_regression_manifest_entry():
    missing = sorted(TOOL_NAMES - set(ASSISTANT_TOOL_COVERAGE))
    stale = sorted(set(ASSISTANT_TOOL_COVERAGE) - TOOL_NAMES)
    assert not missing, f"Add assistant regression coverage entries for new tools: {missing}"
    assert not stale, f"Remove stale assistant regression coverage entries: {stale}"


def test_assistant_core_cases_reference_declared_tool_coverage():
    declared = set(ASSISTANT_TOOL_COVERAGE)
    used = {
        expectation.name
        for case in ASSISTANT_CORE_CASES
        for expectation in case.expected_tools
    }
    missing = sorted(used - declared)
    assert not missing, f"Core cases use tools not listed in ASSISTANT_TOOL_COVERAGE: {missing}"
