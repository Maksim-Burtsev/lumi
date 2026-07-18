"""Idempotent lifecycle for background focus-reflection extraction."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.reflection_extractor import (
    REFLECTION_PROMPT_VERSION,
    REFLECTION_SCHEMA_VERSION,
    ReflectionExtractor,
)
from lumi.db.models import (
    FocusAnalysisStatus,
    FocusSession,
    FocusSessionAnalysis,
)
from lumi.logging import get_logger
from lumi.services.realtime import RealtimeEventService
from lumi.utils.time import utc_now
from lumi.worker.queue import enqueue_job

log = get_logger(__name__)


def reflection_snapshot(focus_session: FocusSession) -> dict[str, Any]:
    """Canonical user-authored source. Stored on each analysis row unchanged."""

    return {
        "outcome": (
            focus_session.reflection_outcome.value if focus_session.reflection_outcome is not None else None
        ),
        "focus_score": focus_session.focus_score,
        "raw_text": focus_session.reflection_text,
        "accomplished_text": focus_session.accomplished_text,
        "distraction_text": focus_session.distraction_text,
        "next_step_text": focus_session.next_step_text,
    }


def reflection_input_hash(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def has_reflection(snapshot: dict[str, Any]) -> bool:
    return any(
        value is not None and (not isinstance(value, str) or bool(value.strip()))
        for value in snapshot.values()
    )


def extraction_source_text(snapshot: dict[str, Any]) -> str:
    labels = (
        ("Raw reflection", "raw_text"),
        ("Accomplished", "accomplished_text"),
        ("Friction", "distraction_text"),
        ("Next action", "next_step_text"),
    )
    return "\n".join(
        f"{label}: {value.strip()}"
        for label, key in labels
        if isinstance((value := snapshot.get(key)), str) and value.strip()
    )


class ReflectionAnalysisService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        extractor: ReflectionExtractor | None = None,
    ) -> None:
        self.session = session
        self._extractor = extractor

    @property
    def extractor(self) -> ReflectionExtractor:
        if self._extractor is None:
            self._extractor = ReflectionExtractor()
        return self._extractor

    async def _emit_status(self, analysis: FocusSessionAnalysis) -> None:
        await RealtimeEventService(self.session).emit(
            user_id=analysis.user_id,
            topics=["focus"],
            event_type=f"focus.reflection_analysis.{analysis.status.value}",
            payload={
                "analysis_id": str(analysis.id),
                "session_id": str(analysis.focus_session_id),
                "status": analysis.status.value,
            },
        )

    async def _supersede(
        self,
        analyses: list[FocusSessionAnalysis],
    ) -> None:
        changed = [analysis for analysis in analyses if analysis.status != FocusAnalysisStatus.SUPERSEDED]
        for analysis in changed:
            analysis.status = FocusAnalysisStatus.SUPERSEDED
        if not changed:
            return
        await self.session.flush()
        for analysis in changed:
            await self._emit_status(analysis)

    async def current_for_sessions(
        self,
        *,
        user_id: uuid.UUID,
        sessions: list[FocusSession],
    ) -> dict[uuid.UUID, FocusSessionAnalysis]:
        session_hashes = {
            item.id: item.reflection_input_hash for item in sessions if item.reflection_input_hash
        }
        if not session_hashes:
            return {}
        result = await self.session.execute(
            select(FocusSessionAnalysis)
            .where(
                FocusSessionAnalysis.user_id == user_id,
                FocusSessionAnalysis.focus_session_id.in_(session_hashes),
                FocusSessionAnalysis.status != FocusAnalysisStatus.SUPERSEDED,
            )
            .order_by(
                FocusSessionAnalysis.created_at.desc(),
                FocusSessionAnalysis.id.desc(),
            )
        )
        current: dict[uuid.UUID, FocusSessionAnalysis] = {}
        for analysis in result.scalars():
            if (
                analysis.focus_session_id not in current
                and analysis.input_hash == session_hashes[analysis.focus_session_id]
            ):
                current[analysis.focus_session_id] = analysis
        return current

    async def schedule(
        self,
        focus_session: FocusSession,
    ) -> FocusSessionAnalysis | None:
        """Create one version row; provider/queue failures never affect finishing."""

        try:
            async with self.session.begin_nested():
                return await self._schedule(focus_session)
        except Exception:  # noqa: BLE001 - reflection save is the primary operation
            log.exception(
                "failed to schedule reflection extraction",
                fields={"focus_session_id": str(focus_session.id)},
            )
            return None

    async def _schedule(
        self,
        focus_session: FocusSession,
    ) -> FocusSessionAnalysis | None:
        snapshot = reflection_snapshot(focus_session)
        previous = await self.session.execute(
            select(FocusSessionAnalysis)
            .where(
                FocusSessionAnalysis.user_id == focus_session.user_id,
                FocusSessionAnalysis.focus_session_id == focus_session.id,
                FocusSessionAnalysis.status != FocusAnalysisStatus.SUPERSEDED,
            )
            .with_for_update()
        )
        previous_rows = list(previous.scalars())
        if not has_reflection(snapshot):
            await self._supersede(previous_rows)
            focus_session.reflection_input_hash = None
            await self.session.flush()
            return None

        digest = reflection_input_hash(snapshot)
        focus_session.reflection_input_hash = digest
        matching = next(
            (
                row
                for row in previous_rows
                if (
                    row.input_hash == digest
                    and row.schema_version == REFLECTION_SCHEMA_VERSION
                    and row.prompt_version == REFLECTION_PROMPT_VERSION
                    and row.model_provider == self.extractor.provider_name
                    and row.model_name == self.extractor.model_name
                )
            ),
            None,
        )
        if matching is not None:
            await self._supersede([row for row in previous_rows if row.id != matching.id])
            return matching
        await self._supersede(previous_rows)

        source_text = extraction_source_text(snapshot)
        analysis = FocusSessionAnalysis(
            user_id=focus_session.user_id,
            focus_session_id=focus_session.id,
            input_hash=digest,
            status=(FocusAnalysisStatus.PENDING if source_text else FocusAnalysisStatus.READY),
            schema_version=REFLECTION_SCHEMA_VERSION,
            prompt_version=REFLECTION_PROMPT_VERSION,
            model_provider=self.extractor.provider_name,
            model_name=self.extractor.model_name,
            source_snapshot=snapshot,
            raw_text_snapshot=snapshot.get("raw_text"),
            outcome=snapshot.get("outcome"),
            outcome_source="user" if snapshot.get("outcome") else None,
            outcome_confidence=1.0 if snapshot.get("outcome") else None,
            completed_at=utc_now() if not source_text else None,
        )
        self.session.add(analysis)
        await self.session.flush()
        if source_text:
            await enqueue_job(
                "extract_focus_reflection",
                str(focus_session.user_id),
                analysis_id=str(analysis.id),
                notify=False,
            )
        else:
            await self._emit_status(analysis)
        return analysis

    async def process(
        self,
        *,
        user_id: uuid.UUID,
        analysis_id: uuid.UUID,
    ) -> FocusSessionAnalysis | None:
        analysis = await self.session.scalar(
            select(FocusSessionAnalysis)
            .where(
                FocusSessionAnalysis.id == analysis_id,
                FocusSessionAnalysis.user_id == user_id,
            )
        )
        if analysis is None:
            return None
        if analysis.status in {
            FocusAnalysisStatus.READY,
            FocusAnalysisStatus.SUPERSEDED,
        }:
            return analysis
        focus_session = await self.session.scalar(
            select(FocusSession).where(
                FocusSession.id == analysis.focus_session_id,
                FocusSession.user_id == user_id,
            )
        )
        if focus_session is None or focus_session.reflection_input_hash != analysis.input_hash:
            locked, _ = await self._lock_processable(
                user_id=user_id,
                analysis_id=analysis_id,
            )
            return locked

        if (
            analysis.model_provider != self.extractor.provider_name
            or analysis.model_name != self.extractor.model_name
        ):
            locked, _ = await self._lock_processable(
                user_id=user_id,
                analysis_id=analysis_id,
            )
            return locked

        source_text = extraction_source_text(analysis.source_snapshot)
        if not source_text:
            locked, current_session = await self._lock_processable(
                user_id=user_id,
                analysis_id=analysis_id,
            )
            if locked is None or current_session is None:
                return locked
            locked.status = FocusAnalysisStatus.READY
            locked.completed_at = utc_now()
            await self.session.flush()
            await self._emit_status(locked)
            return locked

        extracted = None
        extraction_error: Exception | None = None
        try:
            extracted = await self.extractor.extract(
                user_id=user_id,
                source_text=source_text,
                session=self.session,
            )
        except Exception as exc:  # noqa: BLE001 - retry is durable and best-effort
            extraction_error = exc

        locked, current_session = await self._lock_processable(
            user_id=user_id,
            analysis_id=analysis_id,
        )
        if locked is None or current_session is None:
            return locked
        locked.attempt_count += 1
        locked.next_retry_at = None
        locked.last_error_code = None
        if extraction_error is not None:
            locked.status = FocusAnalysisStatus.FAILED
            locked.last_error_code = type(extraction_error).__name__[:120]
            retry_minutes = min(6 * 60, 2 ** min(locked.attempt_count, 8))
            locked.next_retry_at = utc_now() + timedelta(minutes=retry_minutes)
            await self.session.flush()
            await self._emit_status(locked)
            log.warning(
                "reflection extraction failed",
                fields={
                    "analysis_id": str(locked.id),
                    "error_code": locked.last_error_code,
                },
            )
            return locked

        assert extracted is not None
        user_outcome = locked.source_snapshot.get("outcome")
        locked.outcome = user_outcome or extracted.outcome
        locked.outcome_source = "user" if user_outcome else ("model" if extracted.outcome else None)
        locked.outcome_confidence = 1.0 if user_outcome else extracted.outcome_confidence
        locked.work_type = extracted.work_type
        locked.work_type_confidence = extracted.work_type_confidence
        locked.frictions = [friction.model_dump(mode="json") for friction in extracted.frictions]
        locked.normalized_next_action = extracted.normalized_next_action
        locked.next_action_confidence = extracted.next_action_confidence
        locked.evidence = {
            "outcome": extracted.outcome_evidence,
            "work_type": extracted.work_type_evidence,
            "next_action": extracted.next_action_evidence,
        }
        locked.status = FocusAnalysisStatus.READY
        locked.completed_at = utc_now()
        await self.session.flush()
        await self._emit_status(locked)
        return locked

    async def _lock_processable(
        self,
        *,
        user_id: uuid.UUID,
        analysis_id: uuid.UUID,
    ) -> tuple[FocusSessionAnalysis | None, FocusSession | None]:
        analysis = await self.session.scalar(
            select(FocusSessionAnalysis)
            .where(
                FocusSessionAnalysis.id == analysis_id,
                FocusSessionAnalysis.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if analysis is None:
            return None, None
        if analysis.status in {
            FocusAnalysisStatus.READY,
            FocusAnalysisStatus.SUPERSEDED,
        }:
            return analysis, None
        focus_session = await self.session.scalar(
            select(FocusSession)
            .where(
                FocusSession.id == analysis.focus_session_id,
                FocusSession.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        if focus_session is None or focus_session.reflection_input_hash != analysis.input_hash:
            analysis.status = FocusAnalysisStatus.SUPERSEDED
            await self.session.flush()
            await self._emit_status(analysis)
            return analysis, None
        if (
            analysis.model_provider != self.extractor.provider_name
            or analysis.model_name != self.extractor.model_name
        ):
            analysis.status = FocusAnalysisStatus.SUPERSEDED
            await self.session.flush()
            await self._emit_status(analysis)
            await self.schedule(focus_session)
            return analysis, None
        return analysis, focus_session
