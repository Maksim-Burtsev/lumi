from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from lumi.assistant.reflection_extractor import (
    ReflectionExtraction,
    redact_reflection_for_provider,
)
from lumi.db.models import (
    FocusAnalysisStatus,
    FocusSession,
    FocusSessionAnalysis,
    FocusSessionStatus,
    ReflectionOutcome,
    UiEvent,
)
from lumi.db.session import session_scope
from lumi.services.reflection_analysis import ReflectionAnalysisService
from lumi.services.users import UserService
from lumi.utils.time import utc_now

from .conftest import TEST_TELEGRAM_ID


class _Extractor:
    provider_name = "contract"
    model_name = "fixture-v1"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def extract(self, *, user_id, source_text, session):
        del user_id, session
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider unavailable")
        return ReflectionExtraction.model_validate(
            {
                "outcome": "blocked",
                "outcome_confidence": 0.72,
                "outcome_evidence": ["Blocked by API"],
                "work_type": "deep_work",
                "work_type_confidence": 0.91,
                "work_type_evidence": ["API"],
                "frictions": [
                    {
                        "label": "dependency",
                        "confidence": 0.88,
                        "evidence": ["Blocked by API"],
                    }
                ],
                "normalized_next_action": "retry after access",
                "next_action_confidence": 0.8,
                "next_action_evidence": ["retry after access"],
            }
        )


def _completed_session(user_id) -> FocusSession:
    ended_at = utc_now()
    return FocusSession(
        user_id=user_id,
        intention="Finish API integration",
        planned_minutes=25,
        status=FocusSessionStatus.COMPLETED,
        started_at=ended_at - timedelta(minutes=25),
        target_end_at=ended_at,
        ended_at=ended_at,
        duration_seconds=25 * 60,
    )


async def test_reflection_analysis_is_versioned_idempotent_and_user_outcome_wins(
    db_session,
    monkeypatch,
):
    enqueued: list[tuple[tuple, dict]] = []

    async def fake_enqueue(*args, **kwargs):
        enqueued.append((args, kwargs))
        return "job-1"

    monkeypatch.setattr(
        "lumi.services.reflection_analysis.enqueue_job",
        fake_enqueue,
    )
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    focus_session = _completed_session(user.id)
    focus_session.reflection_outcome = ReflectionOutcome.PROGRESS
    focus_session.reflection_text = "Blocked by API; retry after access."
    focus_session.focus_score = 3
    db_session.add(focus_session)
    await db_session.flush()

    extractor = _Extractor()
    service = ReflectionAnalysisService(db_session, extractor=extractor)
    created = await service.schedule(focus_session)
    repeated = await service.schedule(focus_session)

    assert created is not None
    assert repeated is created
    assert created.status == FocusAnalysisStatus.PENDING
    assert created.raw_text_snapshot == "Blocked by API; retry after access."
    assert len(enqueued) == 1

    processed = await service.process(
        user_id=user.id,
        analysis_id=created.id,
    )
    assert processed is not None
    assert processed.status == FocusAnalysisStatus.READY
    assert processed.outcome == "progress"
    assert processed.outcome_source == "user"
    assert float(processed.outcome_confidence or 0) == 1
    assert processed.work_type == "deep_work"
    assert processed.frictions[0]["label"] == "dependency"
    assert processed.evidence["work_type"] == ["API"]
    assert extractor.calls == 1

    old_hash = created.input_hash
    focus_session.reflection_text = "Finished the API safely."
    replacement = await service.schedule(focus_session)
    assert replacement is not None
    assert replacement.id != created.id
    assert replacement.input_hash != old_hash
    assert created.status == FocusAnalysisStatus.SUPERSEDED
    assert created.raw_text_snapshot == "Blocked by API; retry after access."
    events = list(
        (
            await db_session.execute(select(UiEvent).where(UiEvent.user_id == user.id).order_by(UiEvent.id))
        ).scalars()
    )
    assert [event.event_type for event in events] == [
        "focus.reflection_analysis.ready",
        "focus.reflection_analysis.superseded",
    ]


async def test_empty_reflection_does_not_enqueue_or_call_provider(
    db_session,
    monkeypatch,
):
    async def unexpected_enqueue(*args, **kwargs):
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(
        "lumi.services.reflection_analysis.enqueue_job",
        unexpected_enqueue,
    )
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    focus_session = _completed_session(user.id)
    db_session.add(focus_session)
    await db_session.flush()

    extractor = _Extractor()
    analysis = await ReflectionAnalysisService(
        db_session,
        extractor=extractor,
    ).schedule(focus_session)

    assert analysis is None
    assert focus_session.reflection_input_hash is None
    assert extractor.calls == 0


async def test_provider_failure_is_retryable_and_never_changes_source(
    db_session,
    monkeypatch,
):
    async def fake_enqueue(*args, **kwargs):
        return "job-1"

    monkeypatch.setattr(
        "lumi.services.reflection_analysis.enqueue_job",
        fake_enqueue,
    )
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    focus_session = _completed_session(user.id)
    focus_session.reflection_text = "Blocked by API; retry after access."
    db_session.add(focus_session)
    await db_session.flush()

    service = ReflectionAnalysisService(
        db_session,
        extractor=_Extractor(fail=True),
    )
    analysis = await service.schedule(focus_session)
    assert analysis is not None

    processed = await service.process(
        user_id=user.id,
        analysis_id=analysis.id,
    )

    assert processed is not None
    assert processed.status == FocusAnalysisStatus.FAILED
    assert processed.attempt_count == 1
    assert processed.next_retry_at is not None
    assert processed.last_error_code == "RuntimeError"
    assert focus_session.status == FocusSessionStatus.COMPLETED
    assert focus_session.reflection_text == "Blocked by API; retry after access."
    stored = await db_session.scalar(
        select(FocusSessionAnalysis).where(FocusSessionAnalysis.id == analysis.id)
    )
    assert stored is processed
    event = await db_session.scalar(
        select(UiEvent).where(
            UiEvent.user_id == user.id,
            UiEvent.event_type == "focus.reflection_analysis.failed",
        )
    )
    assert event is not None
    assert event.payload["analysis_id"] == str(analysis.id)


async def test_provider_call_does_not_lock_reflection_edit(
    db_session,
    monkeypatch,
):
    async def fake_enqueue(*args, **kwargs):
        return "job-1"

    class BlockingExtractor(_Extractor):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def extract(self, *, user_id, source_text, session):
            del user_id, source_text, session
            self.calls += 1
            self.started.set()
            await self.release.wait()
            return ReflectionExtraction()

    monkeypatch.setattr(
        "lumi.services.reflection_analysis.enqueue_job",
        fake_enqueue,
    )
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    focus_session = _completed_session(user.id)
    focus_session.reflection_text = "Original reflection."
    db_session.add(focus_session)
    await db_session.flush()
    extractor = BlockingExtractor()
    analysis = await ReflectionAnalysisService(
        db_session,
        extractor=extractor,
    ).schedule(focus_session)
    assert analysis is not None
    user_id = user.id
    session_id = focus_session.id
    analysis_id = analysis.id
    await db_session.commit()

    async def process_analysis():
        async with session_scope() as worker_session:
            return await ReflectionAnalysisService(
                worker_session,
                extractor=extractor,
            ).process(user_id=user_id, analysis_id=analysis_id)

    process_task = asyncio.create_task(process_analysis())
    await asyncio.wait_for(extractor.started.wait(), timeout=1)
    try:
        async with session_scope() as edit_session:
            edited = await edit_session.get(FocusSession, session_id)
            assert edited is not None
            edited.reflection_text = "Edited while extraction was running."
            await edit_session.flush()
            replacement = await asyncio.wait_for(
                ReflectionAnalysisService(
                    edit_session,
                    extractor=_Extractor(),
                ).schedule(edited),
                timeout=1,
            )
            assert replacement is not None
            assert replacement.id != analysis_id
    finally:
        extractor.release.set()

    processed = await asyncio.wait_for(process_task, timeout=1)
    assert processed is not None
    assert processed.status == FocusAnalysisStatus.SUPERSEDED


async def test_processor_supersedes_and_reschedules_provider_mismatch(
    db_session,
    monkeypatch,
):
    enqueued: list[dict] = []

    async def fake_enqueue(*args, **kwargs):
        del args
        enqueued.append(kwargs)
        return "job-1"

    class ReplacementExtractor(_Extractor):
        provider_name = "replacement"
        model_name = "fixture-v2"

    monkeypatch.setattr(
        "lumi.services.reflection_analysis.enqueue_job",
        fake_enqueue,
    )
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    focus_session = _completed_session(user.id)
    focus_session.reflection_text = "Blocked by API; retry after access."
    db_session.add(focus_session)
    await db_session.flush()

    original = await ReflectionAnalysisService(
        db_session,
        extractor=_Extractor(),
    ).schedule(focus_session)
    assert original is not None
    replacement_extractor = ReplacementExtractor()

    processed = await ReflectionAnalysisService(
        db_session,
        extractor=replacement_extractor,
    ).process(user_id=user.id, analysis_id=original.id)

    assert processed is original
    assert original.status == FocusAnalysisStatus.SUPERSEDED
    assert replacement_extractor.calls == 0
    replacement = await db_session.scalar(
        select(FocusSessionAnalysis).where(
            FocusSessionAnalysis.focus_session_id == focus_session.id,
            FocusSessionAnalysis.status == FocusAnalysisStatus.PENDING,
        )
    )
    assert replacement is not None
    assert replacement.model_provider == "replacement"
    assert replacement.model_name == "fixture-v2"
    assert len(enqueued) == 2
    event = await db_session.scalar(
        select(UiEvent).where(
            UiEvent.user_id == user.id,
            UiEvent.event_type == "focus.reflection_analysis.superseded",
        )
    )
    assert event is not None


async def test_reflection_processing_is_ownership_scoped(db_session, monkeypatch):
    async def fake_enqueue(*args, **kwargs):
        return "job-1"

    monkeypatch.setattr(
        "lumi.services.reflection_analysis.enqueue_job",
        fake_enqueue,
    )
    users = UserService(db_session)
    owner = await users.ensure_user(TEST_TELEGRAM_ID)
    stranger = await users.ensure_user(TEST_TELEGRAM_ID + 1)
    focus_session = _completed_session(owner.id)
    focus_session.reflection_text = "Blocked by API; retry after access."
    db_session.add(focus_session)
    await db_session.flush()
    service = ReflectionAnalysisService(db_session, extractor=_Extractor())
    analysis = await service.schedule(focus_session)
    assert analysis is not None

    assert await service.process(user_id=stranger.id, analysis_id=analysis.id) is None
    assert analysis.status == FocusAnalysisStatus.PENDING


def test_reflection_golden_corpus_is_labelled_sanitized_and_evidence_literal():
    fixture = Path(__file__).parent / "fixtures" / "reflection_extraction_golden.json"
    cases = json.loads(fixture.read_text())
    assert 30 <= len(cases) <= 50
    assert len({case["id"] for case in cases}) == len(cases)
    assert {case["outcome"] for case in cases} <= {"done", "progress", "blocked"}
    assert {case["work_type"] for case in cases} <= {
        "deep_work",
        "admin",
        "communication",
        "planning",
        "learning",
        "creative",
        "other",
    }
    assert {friction for case in cases for friction in case["frictions"]} <= {
        "interruption",
        "unclear_scope",
        "dependency",
        "energy",
        "environment",
        "tooling",
        "time_pressure",
        "other",
    }
    for case in cases:
        assert "@" not in case["text"]
        assert "api_key=" not in case["text"].lower()
        assert all(evidence in case["text"] for evidence in case["evidence"])


def test_reflection_provider_payload_redacts_direct_secrets_and_contact_ids():
    redacted = redact_reflection_for_provider(
        "Finished. api_key=secret-value email me@example.com bot 123456789012:abcdefghijklmnopqrstuv."
    )
    assert "secret-value" not in redacted
    assert "me@example.com" not in redacted
    assert "abcdefghijklmnopqrstuv" not in redacted
    assert redacted.count("[redacted]") == 3
