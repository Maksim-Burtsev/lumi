from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "agent_cleanup.py"


def load_agent_cleanup():
    spec = importlib.util.spec_from_file_location("agent_cleanup", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cleanup_plan_refuses_default_compose_project_without_override():
    agent_cleanup = load_agent_cleanup()

    with pytest.raises(SystemExit, match="Refusing to clean default compose project"):
        agent_cleanup.CleanupPlan.from_env({}, remove_volumes=False, allow_default=False)


def test_cleanup_plan_targets_only_current_agent_project():
    agent_cleanup = load_agent_cleanup()

    plan = agent_cleanup.CleanupPlan.from_env(
        {
            "COMPOSE_PROJECT_NAME": "lumi_agent_cleanup",
            "COMPOSE_FILE": "docker-compose.yml:/tmp/lumi-agent-cleanup.override.yml",
        },
        remove_volumes=False,
        allow_default=False,
    )

    assert plan.project_name == "lumi_agent_cleanup"
    assert plan.dev_auth_container == "lumi_agent_cleanup-api-dev-auth"
    assert plan.tunnel_session == "lumi_agent_cleanup-cloudflared"
    assert plan.compose_command == ["docker", "compose", "down", "--remove-orphans"]
    assert plan.compose_env["COMPOSE_PROJECT_NAME"] == "lumi_agent_cleanup"
    assert plan.compose_env["COMPOSE_FILE"] == "docker-compose.yml:/tmp/lumi-agent-cleanup.override.yml"
    assert plan.verify_command == [
        "docker",
        "ps",
        "-q",
        "--filter",
        "label=com.docker.compose.project=lumi_agent_cleanup",
    ]


def test_cleanup_plan_can_remove_volumes_for_disposable_agent_runtime():
    agent_cleanup = load_agent_cleanup()

    plan = agent_cleanup.CleanupPlan.from_env(
        {"COMPOSE_PROJECT_NAME": "lumi_disposable"},
        remove_volumes=True,
        allow_default=False,
    )

    assert plan.compose_command == ["docker", "compose", "down", "-v", "--remove-orphans"]
