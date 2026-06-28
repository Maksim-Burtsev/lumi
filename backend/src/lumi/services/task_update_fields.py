"""Resolve agent-facing task update fields into DB TaskService updates."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, time
from typing import Any

from lumi.db.models import Task, User
from lumi.utils.time import local_now, local_to_utc, utc_to_local

TEMPORAL_TASK_UPDATE_KEYS = {
    "due_at_local",
    "due_time_local",
    "reminder_at_local",
    "reminder_time_local",
}


def resolve_task_update_fields(
    *,
    user: User,
    task: Task,
    updates: Mapping[str, Any],
) -> dict[str, Any]:
    resolved = {
        key: value
        for key, value in updates.items()
        if key not in TEMPORAL_TASK_UPDATE_KEYS
    }
    if "due_at_local" in updates:
        due_at = _coerce_datetime(updates.get("due_at_local"))
        if due_at is not None:
            resolved["due_at"] = local_to_utc(due_at, user.timezone)
    elif "due_time_local" in updates:
        due_time = _coerce_time(updates.get("due_time_local"))
        if due_time is not None:
            resolved["due_at"] = _combine_task_date(
                task=task,
                user=user,
                target_time=due_time,
                field="due_at",
            )

    if "reminder_at_local" in updates:
        reminder_at = _coerce_datetime(updates.get("reminder_at_local"))
        if reminder_at is not None:
            resolved["reminder_at"] = local_to_utc(reminder_at, user.timezone)
    elif "reminder_time_local" in updates:
        reminder_time = _coerce_time(updates.get("reminder_time_local"))
        if reminder_time is not None:
            resolved["reminder_at"] = _combine_task_date(
                task=task,
                user=user,
                target_time=reminder_time,
                field="reminder_at",
            )
    return resolved


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _coerce_time(value: Any) -> time | None:
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time().replace(second=0, microsecond=0)
        except ValueError:
            pass
    return None


def _combine_task_date(
    *,
    task: Task,
    user: User,
    target_time: time,
    field: str,
) -> datetime:
    source = getattr(task, field, None) or task.due_at or task.reminder_at
    if source is not None:
        local_date = utc_to_local(source, user.timezone).date()
    else:
        local_date = local_now(user.timezone).date()
    local_dt = datetime.combine(local_date, target_time)
    return local_to_utc(local_dt, user.timezone)
