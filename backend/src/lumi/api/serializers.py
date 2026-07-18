"""Model -> contract-JSON serializers for the Mini App API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from lumi.db.models import (
    AgentRun,
    AssistantSuggestion,
    CalendarEvent,
    FocusInsight,
    FocusSession,
    FocusSessionAnalysis,
    LLMCall,
    Memory,
    Message,
    PendingConfirmation,
    Project,
    Task,
    ToolCall,
    User,
)
from lumi.i18n import ensure_language_settings, normalize_app_locale
from lumi.services.action_policy import policy_for_action, policy_to_dict
from lumi.services.planning_settings import normalize_planning_settings
from lumi.services.tasks import task_bucket
from lumi.utils.time import get_zone


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def user_to_dict(user: User) -> dict[str, Any]:
    settings = ensure_language_settings(user.settings)
    settings["planning"] = normalize_planning_settings(settings)
    return {
        "id": str(user.id),
        "telegram_user_id": user.telegram_user_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "timezone": user.timezone,
        "locale": normalize_app_locale(user.locale),
        "settings": settings,
        "created_at": _iso(user.created_at),
        "last_seen_at": _iso(user.last_seen_at),
    }


def task_to_dict(
    task: Task,
    *,
    timezone: str | None = "UTC",
    now: datetime | None = None,
) -> dict[str, Any]:
    review_skips = (task.metadata_ or {}).get("review_skips")
    if not isinstance(review_skips, dict):
        review_skips = {}
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority.value,
        "project": task.project,
        "project_id": str(task.project_id) if task.project_id else None,
        "tags": list(task.tags or []),
        "due_at": _iso(task.due_at),
        "planned_for": _iso(task.target_at),
        # Transitional alias for older clients. New code uses planned_for.
        "target_at": _iso(task.target_at),
        "reminder_at": _iso(task.reminder_at),
        "snoozed_until": _iso(task.snoozed_until),
        "estimated_minutes": task.estimated_minutes,
        "estimate_source": task.estimate_source,
        "review_skips": {str(key): True for key, value in review_skips.items() if value is True},
        "source": task.source,
        "created_at": _iso(task.created_at),
        "completed_at": _iso(task.completed_at),
        "bucket": task_bucket(task, timezone=timezone, now=now),
    }


def project_to_dict(
    project: Project,
    *,
    active_task_count: int = 0,
    completed_task_count: int = 0,
    estimated_minutes_total: int = 0,
    next_task: Task | None = None,
    health_status: str = "quiet",
    health_reason: str = "",
    timezone: str | None = "UTC",
) -> dict[str, Any]:
    system_key = (project.metadata_ or {}).get("system_key")
    if not isinstance(system_key, str):
        system_key = None
    return {
        "id": str(project.id),
        "name": project.name,
        "status": project.status.value,
        "color": project.color,
        "system_key": system_key,
        "is_system": bool(system_key),
        "active_task_count": active_task_count,
        "completed_task_count": completed_task_count,
        "estimated_minutes_total": estimated_minutes_total,
        "health_status": health_status,
        "health_reason": health_reason,
        "next_task": task_to_dict(next_task, timezone=timezone) if next_task else None,
        "created_at": _iso(project.created_at),
    }


def assistant_suggestion_to_dict(suggestion: AssistantSuggestion) -> dict[str, Any]:
    return {
        "id": str(suggestion.id),
        "kind": suggestion.kind,
        "status": suggestion.status.value,
        "title": suggestion.title,
        "description": suggestion.description,
        "start_at": _iso(suggestion.start_at),
        "end_at": _iso(suggestion.end_at),
        "affected_task_ids": list(suggestion.affected_task_ids or []),
        "payload": suggestion.payload,
        "expires_at": _iso(suggestion.expires_at),
        "decided_at": _iso(suggestion.decided_at),
        "created_at": _iso(suggestion.created_at),
    }


def focus_session_to_dict(
    focus_session: FocusSession,
    task: Task | None = None,
    project: Project | None = None,
    *,
    timezone: str = "UTC",
    analysis: FocusSessionAnalysis | None = None,
) -> dict[str, Any]:
    project_name = project.name if project is not None else focus_session.project_snapshot
    actual_minutes = (
        round(focus_session.duration_seconds / 60, 1)
        if focus_session.duration_seconds is not None
        else None
    )
    break_minutes = focus_session.break_minutes or 0
    preset = {
        (25, 5): "25/5",
        (50, 10): "50/10",
        (90, 15): "90/15",
    }.get((focus_session.planned_minutes, break_minutes), "custom")
    if focus_session.break_started_at is not None and focus_session.break_ended_at is None:
        cycle_phase = "break"
    elif focus_session.status.value == "active":
        cycle_phase = "focus"
    else:
        cycle_phase = "done"
    return {
        "id": str(focus_session.id),
        "status": focus_session.status.value,
        "planned_event_id": (
            str(focus_session.planned_event_id) if focus_session.planned_event_id else None
        ),
        "task": task_to_dict(task, timezone=timezone) if task else None,
        "project_id": str(focus_session.project_id) if focus_session.project_id else None,
        "project_name": project_name,
        # Transitional alias for older Mini App builds. New code uses project_name.
        "project": project_name,
        "intention": focus_session.intention,
        "planned_minutes": focus_session.planned_minutes,
        "actual_minutes": actual_minutes,
        "planned_vs_actual_minutes": (
            round(actual_minutes - focus_session.planned_minutes, 1)
            if actual_minutes is not None
            else None
        ),
        "cycle": {
            "preset": preset if break_minutes else None,
            "focus_minutes": focus_session.planned_minutes,
            "break_minutes": break_minutes,
            "phase": cycle_phase,
            "break_started_at": _iso(focus_session.break_started_at),
            "break_target_end_at": _iso(focus_session.break_target_end_at),
            "break_ended_at": _iso(focus_session.break_ended_at),
        },
        "started_at": _iso(focus_session.started_at),
        "target_end_at": _iso(focus_session.target_end_at),
        "ended_at": _iso(focus_session.ended_at),
        "duration_seconds": focus_session.duration_seconds,
        "local_date": focus_session.started_at.astimezone(get_zone(timezone)).date().isoformat(),
        "reflection": {
            "outcome": (
                focus_session.reflection_outcome.value
                if focus_session.reflection_outcome
                else None
            ),
            "raw_text": focus_session.reflection_text,
            "accomplished_text": focus_session.accomplished_text,
            "distraction_text": focus_session.distraction_text,
            "next_step_text": focus_session.next_step_text,
            "focus_score": focus_session.focus_score,
            "input_hash": focus_session.reflection_input_hash,
            "analysis": (
                {
                    "status": analysis.status.value,
                    "schema_version": analysis.schema_version,
                    "updated_at": _iso(analysis.updated_at),
                }
                if analysis is not None
                else None
            ),
        },
    }


def focus_insight_to_dict(insight: FocusInsight) -> dict[str, Any]:
    return {
        "id": str(insight.id),
        "kind": insight.kind,
        "status": insight.status.value,
        "statement": insight.statement,
        "window_start": _iso(insight.window_start),
        "window_end": _iso(insight.window_end),
        "support_count": insight.support_count,
        "confidence": float(insight.confidence),
        "evidence": {
            **insight.evidence,
            "supporting_session_ids": list(insight.supporting_session_ids),
            "distinct_days": insight.distinct_days,
        },
        "first_seen_at": _iso(insight.first_seen_at),
        "last_seen_at": _iso(insight.last_seen_at),
    }


def event_to_dict(event: CalendarEvent) -> dict[str, Any]:
    metadata = event.metadata_ or {}
    private_note = metadata.get("private_note")
    private_note_summary = metadata.get("private_note_summary")
    if event.source.value == "internal":
        kind = "work_block" if event.source_task_id else "internal"
    else:
        kind = "external"
    raw_work_block_conflict = metadata.get("work_block_conflict")
    work_block_conflict = (
        {
            "status": "impacted",
            "external_event_id": raw_work_block_conflict.get("external_event_id"),
            "alternative_event_id": raw_work_block_conflict.get(
                "alternative_event_id"
            ),
        }
        if isinstance(raw_work_block_conflict, dict)
        and raw_work_block_conflict.get("status") == "impacted"
        else None
    )
    return {
        "id": str(event.id),
        "kind": kind,
        "title": event.title,
        "description": event.description,
        "start_at": _iso(event.start_at),
        "end_at": _iso(event.end_at),
        "all_day": event.all_day,
        "busy": event.busy,
        "status": event.status.value,
        "source": event.source.value,
        "source_task_id": str(event.source_task_id) if event.source_task_id else None,
        "work_block_conflict": work_block_conflict,
        "alternative_for_event_id": metadata.get("alternative_for_event_id"),
        "timezone": event.timezone,
        "created_by": event.created_by,
        "location": metadata.get("location"),
        "meeting_url": metadata.get("meeting_url"),
        "external_url": metadata.get("external_url"),
        "links": list(metadata.get("links") or []),
        "last_synced_at": _iso(event.last_synced_at),
        "organizer": metadata.get("organizer"),
        "attendees": list(metadata.get("attendees") or []),
        "attendee_count": metadata.get("attendee_count", len(metadata.get("attendees") or [])),
        "user_response_status": metadata.get("user_response_status"),
        "private_note": private_note if isinstance(private_note, str) else None,
        "private_note_summary": private_note_summary if isinstance(private_note_summary, str) else None,
        "private_note_summary_status": metadata.get("private_note_summary_status"),
        "private_note_updated_at": metadata.get("private_note_updated_at"),
        "private_note_summary_updated_at": metadata.get("private_note_summary_updated_at"),
        "updated_at": _iso(event.updated_at),
    }


def confirmation_to_dict(confirmation: PendingConfirmation, *, locale: str | None = None) -> dict[str, Any]:
    policy = policy_for_action(confirmation.action_type)
    return {
        "id": str(confirmation.id),
        "action_type": confirmation.action_type,
        "title": confirmation.prompt,
        "status": confirmation.status.value,
        "action_payload": confirmation.action_payload,
        "created_at": _iso(confirmation.created_at),
        "expires_at": _iso(confirmation.expires_at),
        "decided_at": _iso(confirmation.decided_at),
        **policy_to_dict(policy, locale=locale),
    }


def memory_to_dict(memory: Memory) -> dict[str, Any]:
    source = None
    if memory.source_message_id:
        source = "chat"
    elif memory.source_agent_run_id:
        source = "agent"
    return {
        "id": str(memory.id),
        "kind": memory.kind.value,
        "status": memory.status.value,
        "text": memory.text_,
        "tags": list(memory.tags or []),
        "importance": memory.importance,
        "confidence": float(memory.confidence),
        "source": source,
        "created_at": _iso(memory.created_at),
        "last_accessed_at": _iso(memory.last_accessed_at),
    }


def run_to_dict(run: AgentRun) -> dict[str, Any]:
    duration_ms = None
    if run.started_at and run.finished_at:
        duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
    return {
        "id": str(run.id),
        "type": run.type.value,
        "status": run.status.value,
        "trigger": run.trigger,
        "input_summary": run.input_summary,
        "result_summary": run.result_summary,
        "error_message": run.error_message,
        "created_at": _iso(run.created_at),
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "duration_ms": duration_ms,
    }


def tool_call_to_dict(call: ToolCall) -> dict[str, Any]:
    return {
        "id": str(call.id),
        "tool_name": call.tool_name,
        "status": call.status,
        "args_json": call.args_json,
        "result_json": call.result_json,
        "error_message": call.error_message,
        "created_at": _iso(call.created_at),
    }


def llm_call_to_dict(call: LLMCall) -> dict[str, Any]:
    return {
        "id": str(call.id),
        "provider": call.provider,
        "model": call.model,
        "request_kind": call.request_kind,
        "status": call.status,
        "latency_ms": call.latency_ms,
        "input_char_count": call.input_char_count,
        "output_char_count": call.output_char_count,
        "created_at": _iso(call.created_at),
    }


def message_to_dict(message: Message) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "role": message.role.value,
        "content": message.content,
        "created_at": _iso(message.created_at),
    }
