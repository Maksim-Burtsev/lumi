from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from lumi.db.models import (
    CalendarEvent,
    CalendarEventStatus,
    CalendarSource,
    FocusAnalysisStatus,
    FocusInsight,
    FocusInsightStatus,
    FocusSession,
    FocusSessionAnalysis,
    FocusSessionStatus,
    UiEvent,
)
from lumi.services.focus_insights import (
    FocusInsightService,
    InsightCandidate,
    LLMInsightWording,
    insight_wording_payload,
)
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.utils.time import get_zone, utc_now

from .conftest import TEST_TELEGRAM_ID


def _fixture_rows() -> list[dict]:
    fixture = Path(__file__).parent / "fixtures" / "focus_weekly_insights.json"
    return json.loads(fixture.read_text())


async def _seed_week(db_session, user) -> list[FocusSession]:
    task = await TaskService(db_session).create_task(user, title="Weekly fixture")
    zone = get_zone(user.timezone)
    today = utc_now().astimezone(zone).date()
    sessions: list[FocusSession] = []
    for row in _fixture_rows():
        local_start = datetime.combine(
            today - timedelta(days=row["days_ago"]),
            time(hour=row["hour"]),
            tzinfo=zone,
        )
        started_at = local_start.astimezone(UTC)
        planned_end = started_at + timedelta(minutes=row["planned_minutes"])
        work_block = CalendarEvent(
            user_id=user.id,
            source=CalendarSource.INTERNAL,
            title=f"Fixture block {row['id']}",
            start_at=started_at,
            end_at=planned_end,
            timezone=user.timezone,
            busy=True,
            status=CalendarEventStatus.CONFIRMED,
            created_by="fixture",
            source_task_id=task.id,
        )
        db_session.add(work_block)
        if row["after_meeting"]:
            db_session.add(
                CalendarEvent(
                    user_id=user.id,
                    source=CalendarSource.GOOGLE,
                    external_calendar_id="fixture",
                    external_event_id=f"meeting-{row['id']}",
                    title="External meeting",
                    start_at=started_at - timedelta(minutes=60),
                    end_at=started_at - timedelta(minutes=30),
                    timezone=user.timezone,
                    busy=True,
                    status=CalendarEventStatus.CONFIRMED,
                    created_by="sync",
                )
            )
        await db_session.flush()
        ended_at = started_at + timedelta(minutes=row["duration_minutes"])
        focus_session = FocusSession(
            user_id=user.id,
            task_id=task.id,
            planned_event_id=work_block.id,
            intention=f"Fixture session {row['id']}",
            planned_minutes=row["planned_minutes"],
            status=FocusSessionStatus.COMPLETED,
            started_at=started_at,
            target_end_at=planned_end,
            ended_at=ended_at,
            duration_seconds=row["duration_minutes"] * 60,
            focus_score=row["focus_score"],
            reflection_input_hash=(f"hash-{row['id']}" if row["friction"] else None),
        )
        db_session.add(focus_session)
        await db_session.flush()
        sessions.append(focus_session)
        if row["friction"]:
            db_session.add(
                FocusSessionAnalysis(
                    user_id=user.id,
                    focus_session_id=focus_session.id,
                    input_hash=focus_session.reflection_input_hash,
                    status=FocusAnalysisStatus.READY,
                    schema_version="reflection-analysis.v1",
                    prompt_version="reflection-extractor.v1",
                    model_provider="fixture",
                    model_name="fixture-v1",
                    source_snapshot={"raw_text": "Waiting for dependency"},
                    raw_text_snapshot="Waiting for dependency",
                    outcome="progress",
                    outcome_source="user",
                    outcome_confidence=1,
                    work_type="deep_work",
                    work_type_confidence=0.9,
                    frictions=[
                        {
                            "label": row["friction"],
                            "confidence": 0.94,
                            "evidence": ["dependency"],
                        }
                    ],
                    evidence={"work_type": ["dependency"]},
                    completed_at=ended_at,
                )
            )
    await db_session.flush()
    return sessions


async def test_weekly_insights_are_bounded_evidence_backed_and_idempotent(
    db_session,
):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    sessions = await _seed_week(db_session, user)
    service = FocusInsightService(db_session)

    first = await service.list(user, limit=3)
    second = await service.list(user, limit=3)

    assert len(first) == 3
    assert [item.id for item in second] == [item.id for item in first]
    assert {item.kind for item in first} == {
        "planned_actual_gap",
        "daypart_score_association",
        "friction:dependency",
    }
    assert all(item.support_count >= 3 for item in first)
    assert all(item.distinct_days >= 2 for item in first)
    assert all("not a cause" in item.statement or "not a diagnosis" in item.statement for item in first)
    assert await db_session.scalar(select(func.count()).select_from(FocusInsight)) == 3

    aggregate, aggregate_sessions, analyses = await service.aggregates(
        user,
        start=first[0].window_start,
        end=first[0].window_end,
    )
    assert len(aggregate_sessions) == len(sessions) == 28
    assert aggregate["total_sessions"] == 28
    assert aggregate["distinct_days"] == 7
    assert aggregate["break_count"] == 0
    assert len(aggregate["planned_actual"]) == 28
    assert aggregate["project"]["unassigned"]["session_count"] == 28
    assert len(analyses) == 7
    russian = service.candidates(aggregate, locale="ru")
    assert len(russian) == 3
    assert all("не причина" in item.statement or "не диагноз" in item.statement for item in russian)


async def test_try_and_dismiss_only_change_insight_state(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    await _seed_week(db_session, user)
    service = FocusInsightService(db_session)
    insight = (await service.list(user))[0]
    event_count = await db_session.scalar(select(func.count()).select_from(CalendarEvent))
    session_count = await db_session.scalar(select(func.count()).select_from(FocusSession))
    settings_before = dict(user.settings)

    tried = await service.try_insight(user, insight)
    assert tried.status == FocusInsightStatus.CONFIRMED
    assert await service.try_insight(user, insight) is insight
    dismissed = await service.dismiss(user, insight)
    assert dismissed.status == FocusInsightStatus.DISMISSED
    assert await service.dismiss(user, insight) is insight
    assert await db_session.scalar(select(func.count()).select_from(CalendarEvent)) == event_count
    assert await db_session.scalar(select(func.count()).select_from(FocusSession)) == session_count
    assert user.settings == settings_before
    events = list(
        (
            await db_session.execute(
                select(UiEvent)
                .where(
                    UiEvent.user_id == user.id,
                    UiEvent.event_type.in_(["focus.insight_confirmed", "focus.insight_dismissed"]),
                )
                .order_by(UiEvent.id)
            )
        ).scalars()
    )
    assert [event.event_type for event in events] == [
        "focus.insight_confirmed",
        "focus.insight_dismissed",
    ]


async def test_edit_or_delete_changes_context_and_expires_stale_proposal(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    sessions = await _seed_week(db_session, user)
    service = FocusInsightService(db_session)
    original = next(item for item in await service.list(user) if item.kind == "planned_actual_gap")
    original_hash = original.context_hash

    await db_session.delete(sessions[0])
    await db_session.flush()
    await service.refresh(user)

    assert original.status == FocusInsightStatus.EXPIRED
    replacement = await db_session.scalar(
        select(FocusInsight).where(
            FocusInsight.user_id == user.id,
            FocusInsight.kind == "planned_actual_gap",
            FocusInsight.context_hash != original_hash,
            FocusInsight.status == FocusInsightStatus.PROPOSED,
        )
    )
    assert replacement is not None
    assert str(sessions[0].id) not in replacement.supporting_session_ids


async def test_refresh_expires_active_old_window_and_honors_cross_window_dismissal(
    db_session,
):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    await _seed_week(db_session, user)
    service = FocusInsightService(db_session)
    insights = await service.list(user)
    old_active = next(item for item in insights if item.kind == "daypart_score_association")
    dismissed = next(item for item in insights if item.kind == "planned_actual_gap")
    await service.dismiss(user, dismissed)
    dismissed_hash = dismissed.context_hash
    for insight in (old_active, dismissed):
        insight.window_start -= timedelta(days=7)
        insight.window_end -= timedelta(days=7)
    await db_session.flush()

    await service.refresh(user)

    assert old_active.status == FocusInsightStatus.EXPIRED
    assert dismissed.status == FocusInsightStatus.DISMISSED
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(FocusInsight)
            .where(
                FocusInsight.user_id == user.id,
                FocusInsight.context_hash == dismissed_hash,
                FocusInsight.status.in_(
                    [
                        FocusInsightStatus.PROPOSED,
                        FocusInsightStatus.CONFIRMED,
                    ]
                ),
            )
        )
        == 0
    )


async def test_insight_mutations_reject_expired_rows(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    await _seed_week(db_session, user)
    service = FocusInsightService(db_session)
    insight = (await service.list(user))[0]
    insight.expires_at = utc_now() - timedelta(seconds=1)
    await db_session.flush()

    with pytest.raises(ValueError, match="focus_insight_not_available"):
        await service.try_insight(user, insight)
    with pytest.raises(ValueError, match="focus_insight_not_available"):
        await service.dismiss(user, insight)
    assert insight.status == FocusInsightStatus.PROPOSED


async def test_insufficient_sample_and_ownership_are_safe(db_session):
    users = UserService(db_session)
    user = await users.ensure_user(TEST_TELEGRAM_ID)
    stranger = await users.ensure_user(TEST_TELEGRAM_ID + 1)
    now = utc_now()
    for offset in (1, 2):
        db_session.add(
            FocusSession(
                user_id=user.id,
                intention=f"Small sample {offset}",
                planned_minutes=25,
                status=FocusSessionStatus.COMPLETED,
                started_at=now - timedelta(hours=offset),
                target_end_at=now - timedelta(hours=offset) + timedelta(minutes=25),
                ended_at=now - timedelta(hours=offset) + timedelta(minutes=25),
                duration_seconds=25 * 60,
            )
        )
    await db_session.flush()
    service = FocusInsightService(db_session)
    assert await service.list(user) == []
    assert await service.list(stranger) == []


def test_wording_payload_contains_only_controlled_aggregate_evidence():
    candidate = InsightCandidate(
        kind="planned_actual_gap",
        statement="Draft",
        supporting_session_ids=["private-session-id"],
        distinct_days=3,
        confidence=0.8,
        evidence={
            "sessions": [
                {
                    "session_id": "private-session-id",
                    "project": "Private project",
                    "delta_percent": 25,
                }
            ],
            "raw_text": None,
        },
    )
    payload = insight_wording_payload(candidate, locale="ru")
    serialized = json.dumps(payload)
    assert "private-session-id" not in serialized
    assert "Private project" not in serialized
    assert payload["locale"] == "ru"
    assert payload["aggregate_evidence"]["sessions"] == [{"delta_percent": 25}]


async def test_wording_adapter_receives_only_the_prevalidated_payload():
    class FakeLLM:
        def __init__(self) -> None:
            self.payload = None

        async def complete_json(self, **kwargs):
            self.payload = json.loads(kwargs["messages"][0].content)
            return {"statement": self.payload["draft"]}

    fake = FakeLLM()
    payload = {
        "locale": "ru",
        "kind": "planned_actual_gap",
        "draft": "A non-causal observation.",
        "support_count": 5,
        "distinct_days": 3,
        "confidence": 0.8,
        "aggregate_evidence": {"value": 25},
    }
    statement = await LLMInsightWording(fake).format(  # type: ignore[arg-type]
        payload,
        locale="ru",
    )
    assert statement == payload["draft"]
    assert fake.payload == payload
