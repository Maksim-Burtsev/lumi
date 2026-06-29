#!/usr/bin/env python3
"""Clean the Docker runtime owned by one agent QA branch."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Mapping


DEFAULT_PROJECT_NAME = "lumi"
PROTECTED_PROJECT_NAMES = {DEFAULT_PROJECT_NAME, "default"}


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


@dataclass(frozen=True)
class CleanupPlan:
    project_name: str
    compose_env: dict[str, str]
    compose_command: list[str]
    dev_auth_container: str
    remove_dev_auth_command: list[str]
    tunnel_session: str
    kill_tunnel_command: list[str]
    verify_command: list[str]

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str],
        *,
        remove_volumes: bool,
        allow_default: bool,
    ) -> CleanupPlan:
        project_name = _clean(env.get("COMPOSE_PROJECT_NAME")) or DEFAULT_PROJECT_NAME
        if project_name in PROTECTED_PROJECT_NAMES and not allow_default:
            raise SystemExit(
                "Refusing to clean default compose project. Set COMPOSE_PROJECT_NAME=lumi_<task_slug> "
                "or pass --allow-default if you intentionally want to stop the shared local runtime."
            )

        compose_env = {"COMPOSE_PROJECT_NAME": project_name}
        compose_file = _clean(env.get("COMPOSE_FILE"))
        if compose_file:
            compose_env["COMPOSE_FILE"] = compose_file

        compose_command = ["docker", "compose", "down"]
        if remove_volumes:
            compose_command.append("-v")
        compose_command.append("--remove-orphans")

        dev_auth_container = _clean(env.get("LUMI_DEV_AUTH_CONTAINER")) or f"{project_name}-api-dev-auth"
        tunnel_session = _clean(env.get("LUMI_TUNNEL_SESSION")) or f"{project_name}-cloudflared"

        return cls(
            project_name=project_name,
            compose_env=compose_env,
            compose_command=compose_command,
            dev_auth_container=dev_auth_container,
            remove_dev_auth_command=["docker", "rm", "-f", dev_auth_container],
            tunnel_session=tunnel_session,
            kill_tunnel_command=["tmux", "kill-session", "-t", tunnel_session],
            verify_command=[
                "docker",
                "ps",
                "-q",
                "--filter",
                f"label=com.docker.compose.project={project_name}",
            ],
        )


def run_command(
    command: list[str],
    *,
    env: Mapping[str, str] | None = None,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command), flush=True)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        command,
        check=check,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
    )


def run_optional_command(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(
        command,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def execute_cleanup(plan: CleanupPlan) -> int:
    run_command(plan.compose_command, env=plan.compose_env)
    run_optional_command(plan.remove_dev_auth_command)
    run_optional_command(plan.kill_tunnel_command)

    verify = run_command(plan.verify_command, capture_output=True)
    running = verify.stdout.strip()
    if running:
        print(
            f"Containers still running for compose project {plan.project_name}:\n{running}",
            file=sys.stderr,
        )
        return 1
    print(f"No running containers for compose project {plan.project_name}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--volumes",
        action="store_true",
        help="also remove named compose volumes; use only for disposable QA runtimes",
    )
    parser.add_argument(
        "--allow-default",
        action="store_true",
        help="allow cleanup of the default/shared lumi compose project",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the cleanup plan without executing commands",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    plan = CleanupPlan.from_env(
        os.environ,
        remove_volumes=args.volumes,
        allow_default=args.allow_default,
    )
    if args.dry_run:
        print(plan)
        return 0
    return execute_cleanup(plan)


if __name__ == "__main__":
    raise SystemExit(main())
