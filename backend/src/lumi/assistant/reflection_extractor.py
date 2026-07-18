"""Strict, privacy-bounded extraction of facts from a focus reflection."""

from __future__ import annotations

import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.llm.base import LLMMessage
from lumi.llm.gateway import LLMGateway

REFLECTION_SCHEMA_VERSION = "reflection-analysis.v1"
REFLECTION_PROMPT_VERSION = "reflection-extractor.v1"

ReflectionOutcomeValue = Literal["done", "progress", "blocked"]
WorkType = Literal[
    "deep_work",
    "admin",
    "communication",
    "planning",
    "learning",
    "creative",
    "other",
]
FrictionLabel = Literal[
    "interruption",
    "unclear_scope",
    "dependency",
    "energy",
    "environment",
    "tooling",
    "time_pressure",
    "other",
]

_SYSTEM = """\
You extract structured evidence from one completed focus-session reflection.
Return only JSON matching the schema. Never give advice, coaching, diagnoses,
personality claims, or preferences. Use only the supplied text.

Rules:
- outcome is done, progress, blocked, or null;
- work_type is one fixed enum value or null;
- frictions use only the fixed taxonomy;
- normalized_next_action is a short action explicitly stated by the user, or null;
- every evidence span must be a short literal substring of the supplied text;
- use null/empty values when evidence is absent; never infer hidden motivation.
"""

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(bearer|token|api[_ -]?key|password|secret)\s*[:=]\s*\S+"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b\d{12,}:[A-Za-z0-9_-]{20,}\b"),
)


class FrictionExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: FrictionLabel
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list, max_length=3)


class ReflectionExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: ReflectionOutcomeValue | None = None
    outcome_confidence: float | None = Field(default=None, ge=0, le=1)
    outcome_evidence: list[str] = Field(default_factory=list, max_length=3)
    work_type: WorkType | None = None
    work_type_confidence: float | None = Field(default=None, ge=0, le=1)
    work_type_evidence: list[str] = Field(default_factory=list, max_length=3)
    frictions: list[FrictionExtraction] = Field(default_factory=list, max_length=4)
    normalized_next_action: str | None = Field(default=None, max_length=300)
    next_action_confidence: float | None = Field(default=None, ge=0, le=1)
    next_action_evidence: list[str] = Field(default_factory=list, max_length=3)


def redact_reflection_for_provider(value: str) -> str:
    """Remove common direct secrets/contact identifiers before provider input."""

    redacted = value[:6000]
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


def _literal_evidence(items: list[str], source: str) -> list[str]:
    return [
        item.strip()
        for item in items
        if item.strip() and len(item.strip()) <= 180 and item.strip() in source
    ][:3]


def _validate_literal_evidence(
    extracted: ReflectionExtraction,
    *,
    source: str,
) -> ReflectionExtraction:
    extracted.outcome_evidence = _literal_evidence(extracted.outcome_evidence, source)
    extracted.work_type_evidence = _literal_evidence(extracted.work_type_evidence, source)
    extracted.next_action_evidence = _literal_evidence(
        extracted.next_action_evidence,
        source,
    )
    for friction in extracted.frictions:
        friction.evidence = _literal_evidence(friction.evidence, source)
    extracted.frictions = [
        friction for friction in extracted.frictions if friction.evidence
    ]
    if not extracted.outcome_evidence:
        extracted.outcome = None
        extracted.outcome_confidence = None
    if not extracted.work_type_evidence:
        extracted.work_type = None
        extracted.work_type_confidence = None
    if not extracted.next_action_evidence:
        extracted.normalized_next_action = None
        extracted.next_action_confidence = None
    return extracted


class ReflectionExtractor:
    def __init__(self, llm: LLMGateway | None = None) -> None:
        self.llm = llm or LLMGateway()

    @property
    def provider_name(self) -> str:
        return self.llm.provider.name

    @property
    def model_name(self) -> str:
        return getattr(self.llm.provider, "model", "unknown")

    async def extract(
        self,
        *,
        user_id: uuid.UUID,
        source_text: str,
        session: AsyncSession,
    ) -> ReflectionExtraction:
        provider_text = redact_reflection_for_provider(source_text)
        raw = await self.llm.complete_json(
            messages=[LLMMessage(role="user", content=provider_text)],
            system=_SYSTEM,
            json_schema_hint=ReflectionExtraction.model_json_schema(),
            request_kind="reflection_extraction",
            user_id=user_id,
            session=session,
            temperature=0,
            max_tokens=1200,
        )
        extracted = ReflectionExtraction.model_validate(raw)
        return _validate_literal_evidence(extracted, source=provider_text)
