"""Model -> contract-JSON serializers for the Mini App API."""

from __future__ import annotations

from typing import Any

from lumi.db.models import (
    AgentRun,
    CalendarEvent,
    EmailThread,
    LLMCall,
    Memory,
    Message,
    NewsDigestRun,
    NewsTopic,
    PendingConfirmation,
    ScheduledTask,
    Task,
    ToolCall,
    User,
)
from lumi.services.action_policy import policy_for_action, policy_to_dict


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def user_to_dict(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "telegram_user_id": user.telegram_user_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "timezone": user.timezone,
        "locale": user.locale,
        "settings": user.settings,
        "created_at": _iso(user.created_at),
        "last_seen_at": _iso(user.last_seen_at),
    }


def task_to_dict(task: Task) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority.value,
        "project": task.project,
        "tags": list(task.tags or []),
        "due_at": _iso(task.due_at),
        "reminder_at": _iso(task.reminder_at),
        "snoozed_until": _iso(task.snoozed_until),
        "source": task.source,
        "created_at": _iso(task.created_at),
        "completed_at": _iso(task.completed_at),
    }


def event_to_dict(event: CalendarEvent) -> dict[str, Any]:
    metadata = event.metadata_ or {}
    return {
        "id": str(event.id),
        "title": event.title,
        "description": event.description,
        "start_at": _iso(event.start_at),
        "end_at": _iso(event.end_at),
        "all_day": event.all_day,
        "busy": event.busy,
        "status": event.status.value,
        "source": event.source.value,
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
    }


def thread_to_dict(thread: EmailThread) -> dict[str, Any]:
    candidate = (thread.metadata_ or {}).get("task_candidate")
    return {
        "id": str(thread.id),
        "subject": thread.subject,
        "sender": thread.participants[0] if thread.participants else None,
        "snippet": thread.snippet,
        "category": thread.category.value,
        "importance": thread.importance,
        "summary": thread.summary,
        "suggested_action": (thread.metadata_ or {}).get("suggested_action"),
        "last_message_at": _iso(thread.last_message_at),
        "task_candidate": candidate,
    }


def confirmation_to_dict(confirmation: PendingConfirmation) -> dict[str, Any]:
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
        **policy_to_dict(policy),
    }


def topic_to_dict(topic: NewsTopic) -> dict[str, Any]:
    return {
        "id": str(topic.id),
        "title": topic.title,
        "query": topic.query,
        "language": topic.language,
        "enabled": topic.enabled,
        "created_at": _iso(topic.created_at),
    }


def digest_to_dict(digest: NewsDigestRun) -> dict[str, Any]:
    return {
        "id": str(digest.id),
        "title": digest.title,
        "digest_text": digest.digest_text,
        "created_at": _iso(digest.created_at),
    }


def automation_to_dict(automation: ScheduledTask) -> dict[str, Any]:
    return {
        "id": str(automation.id),
        "type": automation.type.value,
        "title": automation.title,
        "cron_expression": automation.cron_expression,
        "timezone": automation.timezone,
        "enabled": automation.enabled,
        "config": automation.config,
        "last_run_at": _iso(automation.last_run_at),
        "next_run_at": _iso(automation.next_run_at),
        "failure_count": automation.failure_count,
        "last_error": automation.last_error,
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
