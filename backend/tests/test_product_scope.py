from __future__ import annotations

from lumi.assistant.tool_registry import TOOL_NAMES
from lumi.main import app
from lumi.worker import jobs
from lumi.worker.main import WorkerSettings

REMOVED_TOOLS = {
    "create_automation",
    "read_automations",
    "update_automation",
    "run_automation",
    "email_triage",
    "read_inbox",
    "read_email_thread",
    "create_task_from_email",
    "news_digest",
    "read_news_topics",
    "create_news_topic",
    "update_news_topic",
    "run_news_digest",
}

REMOVED_JOBS = {
    "run_morning_brief",
    "run_news_digest",
    "run_email_triage",
    "run_task_review",
    "run_custom_prompt",
}


def test_assistant_tool_surface_is_productivity_only():
    assert REMOVED_TOOLS.isdisjoint(TOOL_NAMES)
    assert {
        "create_task",
        "read_tasks",
        "plan_day",
        "read_calendar_events",
        "read_memories",
        "read_settings",
        "read_connectors",
    } <= TOOL_NAMES


def test_worker_keeps_productivity_jobs_without_removed_domains():
    registered = {function.__name__ for function in WorkerSettings.functions}
    registered.update(job.coroutine.__name__ for job in WorkerSettings.cron_jobs)

    assert REMOVED_JOBS.isdisjoint(registered)
    assert {
        "process_assistant_turn",
        "run_daily_planning",
        "run_calendar_sync",
        "send_due_reminders",
        "summarize_calendar_private_note",
    } <= registered
    assert jobs.JOB_BY_AUTOMATION_TYPE == {"calendar_sync": "run_calendar_sync"}


def test_api_surface_exposes_productivity_and_observability_only():
    paths = set(app.openapi()["paths"])

    assert not any(path.startswith("/api/inbox") for path in paths)
    assert not any(path.startswith("/api/news") for path in paths)
    assert not any(path.startswith("/api/automations") for path in paths)
    assert {
        "/api/tasks",
        "/api/calendar/events",
        "/api/connectors/google/auth-url",
        "/api/connectors/google/callback",
        "/api/agent-runs",
        "/api/realtime",
    } <= paths
