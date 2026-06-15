"""SQLAlchemy models for the entire Lumi schema.

Conventions:
- UUID primary keys, timezone-aware timestamps.
- Enums are stored as plain VARCHAR (native_enum=False) with CHECK constraints —
  portable and painless to evolve in migrations.
- JSONB for flexible metadata, never instead of queryable fields.
- Cross-aggregate references that would create FK cycles
  (conversations.summary_current_id, compacted_until_message_id) are plain UUIDs.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SaEnum,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from lumi.db.base import Base, created_at_col, updated_at_col, uuid_pk

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ConversationKind(enum.StrEnum):
    MAIN = "main"
    SYSTEM = "system"
    SCHEDULED = "scheduled"
    DEBUG = "debug"


class MemoryKind(enum.StrEnum):
    PREFERENCE = "preference"
    FACT = "fact"
    PROJECT = "project"
    INSTRUCTION = "instruction"
    CONTACT = "contact"
    WORKFLOW = "workflow"
    OTHER = "other"


class MemoryStatus(enum.StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class TaskStatus(enum.StrEnum):
    INBOX = "inbox"
    ACTIVE = "active"
    DONE = "done"
    CANCELLED = "cancelled"


class Priority(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ScheduledTaskType(enum.StrEnum):
    MORNING_BRIEF = "morning_brief"
    NEWS_DIGEST = "news_digest"
    EMAIL_TRIAGE = "email_triage"
    DAILY_PLANNING = "daily_planning"
    CALENDAR_SYNC = "calendar_sync"
    TASK_REVIEW = "task_review"
    CUSTOM_PROMPT = "custom_prompt"


class AgentRunType(enum.StrEnum):
    CHAT = "chat"
    MORNING_BRIEF = "morning_brief"
    NEWS_DIGEST = "news_digest"
    EMAIL_TRIAGE = "email_triage"
    DAILY_PLANNING = "daily_planning"
    CALENDAR_SYNC = "calendar_sync"
    TASK_REVIEW = "task_review"
    REMINDER = "reminder"
    COMPACTION = "compaction"
    CUSTOM = "custom"


class RunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_CONFIRMATION = "waiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConfirmationStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class CalendarSource(enum.StrEnum):
    INTERNAL = "internal"
    GOOGLE = "google"
    YANDEX = "yandex"


class CalendarEventStatus(enum.StrEnum):
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"
    PROPOSED = "proposed"


class EmailCategory(enum.StrEnum):
    NEEDS_REPLY = "needs_reply"
    WAITING_FOR_ME = "waiting_for_me"
    DECISION_NEEDED = "decision_needed"
    FYI = "fyi"
    NEWSLETTER = "newsletter"
    INVOICE_DOCUMENT = "invoice_document"
    IGNORE = "ignore"
    UNKNOWN = "unknown"


class ConnectorType(enum.StrEnum):
    GOOGLE = "google"
    YANDEX = "yandex"


class ConnectorStatus(enum.StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"
    NEEDS_REAUTH = "needs_reauth"


def str_enum(enum_cls: type[enum.StrEnum], name: str) -> SaEnum:
    """VARCHAR-backed enum column type with a CHECK constraint."""
    return SaEnum(
        enum_cls,
        name=name,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


_JSONB_EMPTY_DICT = text("'{}'::jsonb")
_JSONB_EMPTY_LIST = text("'[]'::jsonb")
_TEXT_ARRAY_EMPTY = text("'{}'::text[]")


# ---------------------------------------------------------------------------
# Core: users / conversations / messages / summaries
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(Text)
    first_name: Mapped[str | None] = mapped_column(Text)
    last_name: Mapped[str | None] = mapped_column(Text)
    language_code: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Europe/Moscow")
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="ru")
    # Multi-user: owners come from ALLOWED_TELEGRAM_USER_IDS (env), everyone else
    # requests access and gets approved by the owner in chat.
    is_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_kind", "user_id", "kind"),
        Index(
            "uq_conversations_main_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("kind = 'main'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[ConversationKind] = mapped_column(
        str_enum(ConversationKind, "conversation_kind"),
        nullable=False,
        default=ConversationKind.MAIN,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, default="Lumi")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    # Plain UUIDs to avoid FK cycles (see module docstring).
    summary_current_id: Mapped[uuid.UUID | None] = mapped_column()
    compacted_until_message_id: Mapped[uuid.UUID | None] = mapped_column()
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_messages_user_created", "user_id", "created_at"),
        Index(
            "ix_messages_telegram_message_id",
            "telegram_message_id",
            postgresql_where=text("telegram_message_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(str_enum(MessageRole, "message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    token_estimate: Mapped[int | None] = mapped_column(Integer)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_compacted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    created_at: Mapped[datetime] = created_at_col()


class TelegramUpdate(Base):
    __tablename__ = "telegram_updates"
    __table_args__ = (
        Index("ix_telegram_updates_user_created", "telegram_user_id", "created_at"),
        Index("ix_telegram_updates_chat_message", "telegram_chat_id", "telegram_message_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    update_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="received")
    created_at: Mapped[datetime] = created_at_col()


class AssistantTurn(Base):
    __tablename__ = "assistant_turns"
    __table_args__ = (
        UniqueConstraint("user_id", "sequence_no", name="uq_assistant_turns_user_sequence"),
        Index("ix_assistant_turns_user_status_sequence", "user_id", "status", "sequence_no"),
        Index("ix_assistant_turns_status_deadline", "status", "debounce_deadline_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="collecting")
    sequence_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    primary_message_id: Mapped[int | None] = mapped_column(BigInteger)
    source_update_ids: Mapped[list[int]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_JSONB_EMPTY_LIST
    )
    source_message_ids: Mapped[list[int]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_JSONB_EMPTY_LIST
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    status_message_id: Mapped[int | None] = mapped_column(BigInteger)
    debounce_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"
    __table_args__ = (
        Index("ix_conversation_summaries_conv_created", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    from_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    to_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_estimate: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    created_at: Mapped[datetime] = created_at_col()


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_user_status_importance", "user_id", "status", "importance"),
        Index("ix_memories_user_kind", "user_id", "kind"),
        Index("ix_memories_tags", "tags", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[MemoryKind] = mapped_column(str_enum(MemoryKind, "memory_kind"), nullable=False)
    status: Mapped[MemoryStatus] = mapped_column(
        str_enum(MemoryStatus, "memory_status"), nullable=False, default=MemoryStatus.ACTIVE
    )
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=_TEXT_ARRAY_EMPTY
    )
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=3)  # 1..5
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=0.80)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    source_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_user_status_due", "user_id", "status", "due_at"),
        Index(
            "ix_tasks_user_reminder",
            "user_id",
            "reminder_at",
            postgresql_where=text("reminder_at IS NOT NULL"),
        ),
        Index("ix_tasks_tags", "tags", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        str_enum(TaskStatus, "task_status"), nullable=False, default=TaskStatus.ACTIVE
    )
    priority: Mapped[Priority] = mapped_column(
        str_enum(Priority, "priority"), nullable=False, default=Priority.MEDIUM
    )
    project: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=_TEXT_ARRAY_EMPTY
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # chat / email / agent / manual / calendar
    source: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    source_ref_type: Mapped[str | None] = mapped_column(Text)
    source_ref_id: Mapped[uuid.UUID | None] = mapped_column()
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    calendar_event_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by: Mapped[str] = mapped_column(Text, nullable=False, default="user")  # user/agent/system
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )

    # Set True once the due-reminder notification was sent (avoids re-sending).
    @property
    def reminder_sent(self) -> bool:
        return bool(self.metadata_.get("reminder_sent_at"))


class TaskEvent(Base):
    __tablename__ = "task_events"
    __table_args__ = (Index("ix_task_events_task_created", "task_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    actor: Mapped[str] = mapped_column(Text, nullable=False)  # user/agent/system
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    created_at: Mapped[datetime] = created_at_col()


# ---------------------------------------------------------------------------
# Automations / agent runs / observability
# ---------------------------------------------------------------------------

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        Index("ix_scheduled_tasks_user_enabled_next", "user_id", "enabled", "next_run_at"),
        Index(
            "ix_scheduled_tasks_next_run",
            "next_run_at",
            postgresql_where=text("enabled = true"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[ScheduledTaskType] = mapped_column(
        str_enum(ScheduledTaskType, "scheduled_task_type"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    cron_expression: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_user_created", "user_id", "created_at"),
        Index("ix_agent_runs_user_type_created", "user_id", "type", "created_at"),
        Index("ix_agent_runs_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[AgentRunType] = mapped_column(str_enum(AgentRunType, "agent_run_type"), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        str_enum(RunStatus, "run_status"), nullable=False, default=RunStatus.QUEUED
    )
    # telegram_message / scheduled_task / manual_api / system
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scheduled_tasks.id"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"))
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    input_summary: Mapped[str | None] = mapped_column(Text)
    result_summary: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )


class LLMCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (Index("ix_llm_calls_run_created", "agent_run_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    request_kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # success/error/timeout
    input_char_count: Mapped[int | None] = mapped_column(Integer)
    output_char_count: Mapped[int | None] = mapped_column(Integer)
    input_token_estimate: Mapped[int | None] = mapped_column(Integer)
    output_token_estimate: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    request_hash: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    created_at: Mapped[datetime] = created_at_col()


class ToolCall(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        Index("ix_tool_calls_run_created", "agent_run_id", "created_at"),
        Index("ix_tool_calls_user_tool_created", "user_id", "tool_name", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    agent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    # planned/executed/completed/failed/requires_confirmation/skipped
    status: Mapped[str] = mapped_column(Text, nullable=False)
    args_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pending_confirmations.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class PendingConfirmation(Base):
    __tablename__ = "pending_confirmations"
    __table_args__ = (Index("ix_pending_confirmations_user_status", "user_id", "status", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    action_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ConfirmationStatus] = mapped_column(
        str_enum(ConfirmationStatus, "confirmation_status"),
        nullable=False,
        default=ConfirmationStatus.PENDING,
    )
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __table_args__ = (
        Index("ix_calendar_events_user_start_end", "user_id", "start_at", "end_at"),
        Index("ix_calendar_events_user_source_ext", "user_id", "source", "external_event_id"),
        Index(
            "uq_calendar_events_external",
            "user_id",
            "source",
            "external_calendar_id",
            "external_event_id",
            unique=True,
            postgresql_where=text("external_event_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    source: Mapped[CalendarSource] = mapped_column(
        str_enum(CalendarSource, "calendar_source"), nullable=False
    )
    external_calendar_id: Mapped[str | None] = mapped_column(Text)
    external_event_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    busy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[CalendarEventStatus] = mapped_column(
        str_enum(CalendarEventStatus, "calendar_event_status"),
        nullable=False,
        default=CalendarEventStatus.CONFIRMED,
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False, default="user")
    source_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"))
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


# ---------------------------------------------------------------------------
# Connectors / email
# ---------------------------------------------------------------------------

class Connector(Base):
    __tablename__ = "connectors"
    __table_args__ = (UniqueConstraint("user_id", "type", name="uq_connectors_user_type"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[ConnectorType] = mapped_column(str_enum(ConnectorType, "connector_type"), nullable=False)
    status: Mapped[ConnectorStatus] = mapped_column(
        str_enum(ConnectorStatus, "connector_status"),
        nullable=False,
        default=ConnectorStatus.DISCONNECTED,
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=_TEXT_ARRAY_EMPTY
    )
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    credentials_file_path: Mapped[str | None] = mapped_column(Text)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class EmailThread(Base):
    __tablename__ = "email_threads"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "external_thread_id", name="uq_email_threads_external"),
        Index("ix_email_threads_user_last_message", "user_id", "last_message_at"),
        Index("ix_email_threads_user_category", "user_id", "category"),
        Index("ix_email_threads_labels", "labels", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, default="google")
    external_thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str | None] = mapped_column(Text)
    participants: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_JSONB_EMPTY_LIST
    )
    labels: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=_TEXT_ARRAY_EMPTY
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snippet: Mapped[str | None] = mapped_column(Text)
    category: Mapped[EmailCategory] = mapped_column(
        str_enum(EmailCategory, "email_category"), nullable=False, default=EmailCategory.UNKNOWN
    )
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    triage_status: Mapped[str] = mapped_column(Text, nullable=False, default="new")
    summary: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class EmailMessage(Base):
    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "external_message_id", name="uq_email_messages_external"),
        Index("ix_email_messages_thread_date", "thread_id", "date_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("email_threads.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, default="google")
    external_message_id: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str | None] = mapped_column(Text)
    recipients: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_JSONB_EMPTY_LIST
    )
    cc: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_JSONB_EMPTY_LIST
    )
    subject: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)  # only stored when STORE_EMAIL_BODIES=true
    date_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    created_at: Mapped[datetime] = created_at_col()


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

class NewsTopic(Base):
    __tablename__ = "news_topics"
    __table_args__ = (Index("ix_news_topics_user_enabled", "user_id", "enabled"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False, default="ru")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("user_id", "hash", name="uq_news_items_user_hash"),
        Index("ix_news_items_user_published", "user_id", "published_at"),
        Index("ix_news_items_topic_published", "topic_id", "published_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("news_topics.id"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snippet: Mapped[str | None] = mapped_column(Text)
    content_summary: Mapped[str | None] = mapped_column(Text)
    hash: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    created_at: Mapped[datetime] = created_at_col()


class NewsDigestRun(Base):
    __tablename__ = "news_digest_runs"
    __table_args__ = (Index("ix_news_digest_runs_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    digest_text: Mapped[str] = mapped_column(Text, nullable=False)
    items_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_JSONB_EMPTY_LIST
    )
    created_at: Mapped[datetime] = created_at_col()


# ---------------------------------------------------------------------------
# Files / audit
# ---------------------------------------------------------------------------

class File(Base):
    __tablename__ = "files"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(Text)
    local_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    created_at: Mapped[datetime] = created_at_col()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    actor: Mapped[str] = mapped_column(Text, nullable=False)  # user/agent/system
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    action: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_JSONB_EMPTY_DICT
    )
    created_at: Mapped[datetime] = created_at_col()
