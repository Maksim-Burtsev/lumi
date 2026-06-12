"""Pydantic models for structured LLM outputs (signal extraction, triage, planning)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ExtractedTask(BaseModel):
    title: str
    description: str | None = None
    due_at_local: datetime | None = None
    reminder_at_local: datetime | None = None
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    project: str | None = None
    tags: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    requires_confirmation: bool = True

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty task title")
        return v[:300]


class MemoryCandidate(BaseModel):
    kind: Literal["preference", "fact", "project", "instruction", "contact", "workflow", "other"] = "other"
    text: str
    importance: int = Field(default=3, ge=1, le=5)
    confidence: float = 0.0
    requires_confirmation: bool = True

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty memory text")
        return v[:2000]


class TimeWindow(BaseModel):
    start: datetime
    end: datetime


class CalendarRequest(BaseModel):
    kind: Literal["find_focus_slot", "create_internal_block", "create_external_event", "plan_day"]
    title: str | None = None
    duration_minutes: int = 60
    start_at_local: datetime | None = None
    end_at_local: datetime | None = None
    time_window_local: TimeWindow | None = None
    requires_confirmation: bool = True
    confidence: float = 0.0


class AutomationRequest(BaseModel):
    type: Literal["news_digest", "email_triage", "daily_planning", "calendar_sync", "task_review", "custom_prompt"]
    title: str
    cron_expression: str | None = None
    timezone: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = True
    confidence: float = 0.0


class EmailRequest(BaseModel):
    kind: Literal["triage", "summarize", "find"]
    time_window: str | None = None
    confidence: float = 0.0


class NewsRequest(BaseModel):
    kind: Literal["digest", "add_topic"]
    topics: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class ExtractedSignals(BaseModel):
    """Validated output of the SignalExtractor LLM call."""

    language: str = "ru"
    intents: list[str] = Field(default_factory=lambda: ["chat"])
    tasks: list[ExtractedTask] = Field(default_factory=list)
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    calendar_requests: list[CalendarRequest] = Field(default_factory=list)
    automation_requests: list[AutomationRequest] = Field(default_factory=list)
    email_requests: list[EmailRequest] = Field(default_factory=list)
    news_requests: list[NewsRequest] = Field(default_factory=list)
    should_answer_normally: bool = True

    @classmethod
    def empty(cls) -> ExtractedSignals:
        return cls()


# --- Email triage output -----------------------------------------------------

class TriageTaskCandidate(BaseModel):
    title: str
    due_at_local: datetime | None = None
    priority: Literal["low", "medium", "high", "urgent"] = "medium"


class TriageThreadResult(BaseModel):
    external_thread_id: str
    category: Literal[
        "needs_reply", "waiting_for_me", "decision_needed", "fyi",
        "newsletter", "invoice_document", "ignore", "unknown",
    ] = "unknown"
    importance: int = Field(default=3, ge=1, le=5)
    reason: str | None = None
    suggested_action: str | None = None
    task_candidate: TriageTaskCandidate | None = None


class TriageResult(BaseModel):
    summary: str = ""
    threads: list[TriageThreadResult] = Field(default_factory=list)
    telegram_digest: str = ""


# --- Daily planning output ---------------------------------------------------

class PlannedBlock(BaseModel):
    title: str
    start_at_local: datetime
    end_at_local: datetime
    task_id: str | None = None
    reason: str | None = None


class PlanResult(BaseModel):
    summary: str = ""
    blocks: list[PlannedBlock] = Field(default_factory=list)
