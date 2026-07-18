"""Strict model-facing command contract for the productivity assistant.

The orchestrator still executes a small set of legacy tool names. This module is
the compatibility boundary: the model sees only the commands declared here,
their arguments are locally validated, and validated commands are converted to
the existing executor format.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateTaskArgs(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    project: str | None = Field(default=None, max_length=100)
    project_ref: Literal[
        "last_task_project",
        "last_created_task_project",
        "last_proposed_task_project",
        "last_touched_task_project",
    ] | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    due_at_local: datetime | None = None
    reminder_at_local: datetime | None = None


class ReadTasksArgs(StrictModel):
    filter: Literal["all", "today", "upcoming", "inbox", "done"] = "all"
    limit: int = Field(default=10, ge=1, le=20)


class TaskUpdates(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    project: str | None = Field(default=None, max_length=100)
    tags: list[str] | None = Field(default=None, max_length=20)
    priority: Literal["low", "medium", "high", "urgent"] | None = None
    status: Literal["active", "inbox", "done", "cancelled"] | None = None
    due_at_local: datetime | None = None
    due_time_local: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    reminder_at_local: datetime | None = None
    reminder_time_local: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")

    @model_validator(mode="after")
    def has_update(self) -> TaskUpdates:
        if not self.model_fields_set:
            raise ValueError("at least one task update is required")
        return self


class UpdateTaskArgs(StrictModel):
    task_id: uuid.UUID | None = None
    task_query: str | None = Field(default=None, min_length=1, max_length=300)
    recency_hint: Literal[
        "last_created_task",
        "last_touched_task",
        "last_notified_task",
        "replied_task",
    ] | None = None
    updates: TaskUpdates

    @model_validator(mode="after")
    def has_target(self) -> UpdateTaskArgs:
        if not (self.task_id or self.task_query or self.recency_hint):
            raise ValueError("task target is required")
        return self


class BulkTaskUpdates(StrictModel):
    description: str | None = Field(default=None, max_length=2000)
    project: str | None = Field(default=None, max_length=100)
    tags: list[str] | None = Field(default=None, max_length=20)
    tags_add: list[str] | None = Field(default=None, max_length=20)
    tags_remove: list[str] | None = Field(default=None, max_length=20)
    priority: Literal["low", "medium", "high", "urgent"] | None = None
    status: Literal["active", "inbox", "done", "cancelled"] | None = None

    @model_validator(mode="after")
    def has_update(self) -> BulkTaskUpdates:
        if not self.model_fields_set:
            raise ValueError("at least one bulk task update is required")
        return self


class BulkUpdateTasksArgs(StrictModel):
    task_query: str | None = Field(default=None, min_length=1, max_length=300)
    from_project: str | None = Field(default=None, min_length=1, max_length=100)
    from_tags: list[str] | None = Field(default=None, max_length=20)
    status: Literal["open", "all"] = "open"
    limit: int = Field(default=50, ge=1, le=100)
    updates: BulkTaskUpdates

    @model_validator(mode="after")
    def has_filter(self) -> BulkUpdateTasksArgs:
        if not (self.task_query or self.from_project or self.from_tags):
            raise ValueError("bulk update filter is required")
        return self


class ReadCalendarEventsArgs(StrictModel):
    start_at_local: datetime
    end_at_local: datetime
    include_details: bool = False
    sync_if_needed: bool = True

    @model_validator(mode="after")
    def end_after_start(self) -> ReadCalendarEventsArgs:
        if self.end_at_local <= self.start_at_local:
            raise ValueError("end_at_local must be after start_at_local")
        return self


class CreateCalendarEventArgs(StrictModel):
    destination: Literal["internal", "external"]
    title: str = Field(min_length=1, max_length=300)
    start_at_local: datetime
    end_at_local: datetime
    description: str | None = Field(default=None, max_length=2000)
    private_note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def valid_event(self) -> CreateCalendarEventArgs:
        if self.end_at_local <= self.start_at_local:
            raise ValueError("end_at_local must be after start_at_local")
        if self.destination == "external" and self.private_note is not None:
            raise ValueError("private_note is only valid for internal calendar blocks")
        return self


class UpdateCalendarEventArgs(StrictModel):
    operation: Literal["event", "private_note"] = "event"
    event_id: uuid.UUID | None = None
    event_query: str | None = Field(default=None, min_length=1, max_length=300)
    recency_hint: Literal[
        "last_created_calendar_block",
        "last_touched_calendar_event",
    ] | None = None
    start_at_local: datetime | None = None
    start_time_local: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    shift_minutes: int | None = Field(default=None, ge=-1440, le=1440)
    end_at_local: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=1440)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    private_note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def has_target_and_valid_update(self) -> UpdateCalendarEventArgs:
        if not (self.event_id or self.event_query or self.recency_hint):
            raise ValueError("calendar event target is required")
        schedule_fields = (
            self.start_at_local,
            self.start_time_local,
            self.shift_minutes,
            self.end_at_local,
            self.duration_minutes,
            self.title,
            self.description,
        )
        if self.operation == "private_note":
            if self.private_note is None or any(value is not None for value in schedule_fields):
                raise ValueError("private_note update must contain only private_note")
        elif self.private_note is not None or not any(value is not None for value in schedule_fields):
            raise ValueError("calendar event update is required")
        return self


class CancelCalendarEventArgs(StrictModel):
    event_id: uuid.UUID | None = None
    event_query: str | None = Field(default=None, min_length=1, max_length=300)
    recency_hint: Literal[
        "last_created_calendar_block",
        "last_touched_calendar_event",
    ] | None = None

    @model_validator(mode="after")
    def has_target(self) -> CancelCalendarEventArgs:
        if not (self.event_id or self.event_query or self.recency_hint):
            raise ValueError("calendar event target is required")
        return self


class ReadFocusStateArgs(StrictModel):
    pass


class StartFocusSessionArgs(StrictModel):
    intention: str = Field(min_length=1, max_length=300)
    planned_minutes: int = Field(ge=1, le=240)
    break_minutes: int = Field(default=0, ge=0, le=60)
    task_id: uuid.UUID | None = None
    planned_event_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = Field(default=None, min_length=1, max_length=200)


class FinishFocusSessionArgs(StrictModel):
    session_id: uuid.UUID | None = None
    reflection_outcome: Literal["done", "progress", "blocked"] | None = None
    reflection_text: str | None = Field(default=None, max_length=4000)
    accomplished_text: str | None = Field(default=None, max_length=2000)
    distraction_text: str | None = Field(default=None, max_length=2000)
    next_step_text: str | None = Field(default=None, max_length=1000)
    focus_score: int | None = Field(default=None, ge=1, le=5)


class FinishFocusBreakArgs(StrictModel):
    session_id: uuid.UUID | None = None


class PlanDayArgs(StrictModel):
    date_local: date | None = None


class ManagePreferenceArgs(StrictModel):
    operation: Literal["remember", "read", "update", "forget"]
    explicit_user_request: Literal[True]
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    query: str | None = Field(default=None, min_length=1, max_length=300)
    preference_id: uuid.UUID | None = None
    importance: int | None = Field(default=None, ge=1, le=5)
    limit: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def fields_match_operation(self) -> ManagePreferenceArgs:
        if self.operation == "remember" and self.text is None:
            raise ValueError("remember requires text")
        if self.operation in {"update", "forget"} and self.preference_id is None:
            raise ValueError(f"{self.operation} requires preference_id")
        if self.operation == "update" and self.text is None and self.importance is None:
            raise ValueError("update requires text or importance")
        return self


class CommandBase(StrictModel):
    confidence: float = Field(ge=0.0, le=1.0)
    requires_confirmation: bool = False
    source: Literal["text"] = "text"
    evidence: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("evidence")
    @classmethod
    def clean_evidence(cls, value: list[str]) -> list[str]:
        return [" ".join(item.split()).strip()[:500] for item in value if item.strip()]


class CreateTaskCommand(CommandBase):
    command: Literal["create_task"]
    args: CreateTaskArgs


class ReadTasksCommand(CommandBase):
    command: Literal["read_tasks"]
    args: ReadTasksArgs


class UpdateTaskCommand(CommandBase):
    command: Literal["update_task"]
    args: UpdateTaskArgs


class BulkUpdateTasksCommand(CommandBase):
    command: Literal["bulk_update_tasks"]
    args: BulkUpdateTasksArgs


class ReadCalendarEventsCommand(CommandBase):
    command: Literal["read_calendar_events"]
    args: ReadCalendarEventsArgs


class CreateCalendarEventCommand(CommandBase):
    command: Literal["create_calendar_event"]
    args: CreateCalendarEventArgs


class UpdateCalendarEventCommand(CommandBase):
    command: Literal["update_calendar_event"]
    args: UpdateCalendarEventArgs


class CancelCalendarEventCommand(CommandBase):
    command: Literal["cancel_calendar_event"]
    args: CancelCalendarEventArgs


class ReadFocusStateCommand(CommandBase):
    command: Literal["read_focus_state"]
    args: ReadFocusStateArgs


class StartFocusSessionCommand(CommandBase):
    command: Literal["start_focus_session"]
    args: StartFocusSessionArgs


class FinishFocusSessionCommand(CommandBase):
    command: Literal["finish_focus_session"]
    args: FinishFocusSessionArgs


class FinishFocusBreakCommand(CommandBase):
    command: Literal["finish_focus_break"]
    args: FinishFocusBreakArgs


class PlanDayCommand(CommandBase):
    command: Literal["plan_day"]
    args: PlanDayArgs


class ManagePreferenceCommand(CommandBase):
    command: Literal["manage_preference"]
    args: ManagePreferenceArgs


AssistantCommand = Annotated[
    CreateTaskCommand
    | ReadTasksCommand
    | UpdateTaskCommand
    | BulkUpdateTasksCommand
    | ReadCalendarEventsCommand
    | CreateCalendarEventCommand
    | UpdateCalendarEventCommand
    | CancelCalendarEventCommand
    | ReadFocusStateCommand
    | StartFocusSessionCommand
    | FinishFocusSessionCommand
    | FinishFocusBreakCommand
    | PlanDayCommand
    | ManagePreferenceCommand,
    Field(discriminator="command"),
]


ProgressKind = Literal[
    "understanding",
    "reading_calendar",
    "resolving",
    "writing",
    "answering",
]


class DecisionBase(StrictModel):
    language: str = Field(default="en", min_length=2, max_length=12)
    user_visible_status: str | None = Field(default=None, max_length=80)
    progress_kind: ProgressKind | None = None


class CommandsDecision(DecisionBase):
    kind: Literal["commands"]
    commands: list[AssistantCommand] = Field(min_length=1, max_length=8)
    should_answer_normally: bool = False

    @model_validator(mode="after")
    def writes_are_confident(self) -> CommandsDecision:
        for command in self.commands:
            is_write = (
                command.command != "manage_preference"
                and command.command in WRITE_COMMAND_NAMES
            ) or (
                command.command == "manage_preference"
                and command.args.operation != "read"
            )
            if is_write and command.confidence < 0.6:
                raise ValueError("write command confidence must be at least 0.6")
        return self


class FinalDecision(DecisionBase):
    kind: Literal["final"]
    answer: str = Field(min_length=1, max_length=2000)


class AskDecision(DecisionBase):
    kind: Literal["ask"]
    question: str = Field(min_length=1, max_length=500)
    reason: Literal["ambiguous", "missing_detail", "unsafe"] = "missing_detail"


class DeniedDecision(DecisionBase):
    kind: Literal["denied"]
    reason: Literal[
        "unsupported",
        "research",
        "email",
        "automation",
        "untrusted_instruction",
        "policy",
    ]


AssistantDecision = Annotated[
    CommandsDecision | FinalDecision | AskDecision | DeniedDecision,
    Field(discriminator="kind"),
]

ASSISTANT_DECISION_ADAPTER: TypeAdapter[AssistantDecision] = TypeAdapter(
    AssistantDecision
)

CommandStatus = Literal[
    "success",
    "requires_confirmation",
    "denied",
    "error",
    "timeout",
    "conflict",
    "not_found",
]

class AssistantCommandResult(StrictModel):
    command: str
    status: CommandStatus
    summary: str = Field(default="", max_length=1200)
    data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = Field(default=None, max_length=120)
    retryable: bool = False


VISIBLE_COMMAND_NAMES = frozenset({
    "create_task",
    "read_tasks",
    "update_task",
    "bulk_update_tasks",
    "read_calendar_events",
    "create_calendar_event",
    "update_calendar_event",
    "cancel_calendar_event",
    "read_focus_state",
    "start_focus_session",
    "finish_focus_session",
    "finish_focus_break",
    "plan_day",
    "manage_preference",
})

WRITE_COMMAND_NAMES = frozenset({
    "create_task",
    "update_task",
    "bulk_update_tasks",
    "create_calendar_event",
    "update_calendar_event",
    "cancel_calendar_event",
    "start_focus_session",
    "finish_focus_session",
    "finish_focus_break",
    "plan_day",
    "manage_preference",
})


def is_write_command(command: AssistantCommand) -> bool:
    if command.command == "manage_preference":
        return command.args.operation != "read"
    return command.command in WRITE_COMMAND_NAMES


def parse_assistant_decision(raw: object) -> AssistantDecision:
    return ASSISTANT_DECISION_ADAPTER.validate_python(raw)


def _legacy_command(command: AssistantCommand) -> tuple[str, dict[str, Any], bool]:
    # exclude_unset preserves an explicit null, which is how users clear task
    # fields such as deadlines, reminders, descriptions, and projects.
    args = command.args.model_dump(mode="json", exclude_unset=True)
    requires_confirmation = command.requires_confirmation

    if command.command == "create_calendar_event":
        destination = args.pop("destination")
        if destination == "external":
            requires_confirmation = True
            return "create_external_calendar_event", args, requires_confirmation
        return "create_internal_calendar_block", args, requires_confirmation

    if command.command == "update_calendar_event":
        operation = args.pop("operation", "event")
        if operation == "private_note":
            return "update_calendar_private_note", args, requires_confirmation
        args.pop("private_note", None)
        return "update_calendar_event", args, requires_confirmation

    if command.command == "manage_preference":
        operation = args.pop("operation")
        args.pop("explicit_user_request")
        if operation == "remember":
            args.pop("query", None)
            args.pop("preference_id", None)
            args.pop("limit", None)
            return "store_memory", {"kind": "preference", **args}, requires_confirmation
        if operation == "read":
            query = args.get("query")
            limit = args.get("limit", 5)
            return "read_memories", {"query": query, "kind": "preference", "limit": limit}, False
        preference_id = args.pop("preference_id")
        args.pop("query", None)
        args.pop("limit", None)
        if operation == "update":
            return "update_memory", {"memory_id": preference_id, "kind": "preference", **args}, (
                requires_confirmation
            )
        return "delete_memory", {"memory_id": preference_id}, requires_confirmation

    return command.command, args, requires_confirmation


def decision_to_agent_plan_data(decision: AssistantDecision) -> dict[str, Any]:
    common = {
        "language": decision.language,
        "user_visible_status": decision.user_visible_status,
        "progress_kind": decision.progress_kind,
        "command_core": True,
    }
    if isinstance(decision, CommandsDecision):
        calls: list[dict[str, Any]] = []
        for command in decision.commands:
            name, args, requires_confirmation = _legacy_command(command)
            calls.append({
                "name": name,
                "args": args,
                "confidence": command.confidence,
                "requires_confirmation": requires_confirmation,
                "source": "text",
                "evidence": [f"command_core:{command.command}", *command.evidence],
            })
        return {
            **common,
            "mode": "tool_calls",
            "tool_calls": calls,
            "should_answer_normally": decision.should_answer_normally,
        }
    if isinstance(decision, FinalDecision):
        return {
            **common,
            "mode": "final_answer",
            "final_answer": decision.answer,
            "should_answer_normally": True,
        }
    if isinstance(decision, AskDecision):
        return {
            **common,
            "mode": "ask_user",
            "final_answer": decision.question,
            "should_answer_normally": True,
        }
    return {
        **common,
        "mode": "out_of_scope",
        "should_answer_normally": False,
    }


def command_result(
    *,
    command: str,
    status: str,
    summary: str = "",
    data: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> AssistantCommandResult:
    status_map: dict[str, CommandStatus] = {
        "completed": "success",
        "requires_confirmation": "requires_confirmation",
        "skipped": "denied",
        "failed": "error",
        "timeout": "timeout",
        "conflict": "conflict",
        "not_found": "not_found",
    }
    normalized_status = status_map.get(status, "error")
    return AssistantCommandResult(
        command=command,
        status=normalized_status,
        summary=summary,
        data=data or {},
        error_code=error_code,
        retryable=normalized_status in {"error", "timeout"},
    )
