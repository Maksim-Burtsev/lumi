from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from lumi.api.deps import get_current_user
from lumi.assistant.reflection_extractor import ReflectionExtraction
from lumi.db.models import (
    CalendarEvent,
    CalendarEventStatus,
    CalendarSource,
    FocusAnalysisStatus,
    FocusSession,
    FocusSessionAnalysis,
    FocusSessionStatus,
    Task,
)
from lumi.db.session import session_scope
from lumi.main import app
from lumi.services.planning import PlanningService
from lumi.services.reflection_analysis import ReflectionAnalysisService
from lumi.services.users import UserService

from .conftest import TEST_TELEGRAM_ID


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class _PlanGateway:
    def __init__(self, *, task_id: str, start_at: datetime) -> None:
        self.task_id = task_id
        self.start_at = start_at

    async def complete_json(self, **_kwargs):
        return {
            "summary": "One safe block",
            "blocks": [
                {
                    "title": "Ship Product V2",
                    "task_id": self.task_id,
                    "start_at_local": self.start_at.replace(tzinfo=None).isoformat(),
                    "end_at_local": (
                        self.start_at + timedelta(minutes=25)
                    ).replace(tzinfo=None).isoformat(),
                }
            ],
        }


class _ReflectionExtractor:
    provider_name = "contract"
    model_name = "fixture-v1"

    async def extract(self, **_kwargs):
        return ReflectionExtraction.model_validate(
            {
                "outcome": "progress",
                "outcome_confidence": 0.9,
                "outcome_evidence": ["Completed the integration loop"],
                "work_type": "deep_work",
                "work_type_confidence": 0.9,
                "work_type_evidence": ["integration loop"],
                "frictions": [],
                "normalized_next_action": "run owner dogfood",
                "next_action_confidence": 0.85,
                "next_action_evidence": ["Next: owner dogfood"],
            }
        )


@pytest.fixture
async def client(user):
    async def _override_user():
        async with session_scope() as session:
            return await UserService(session).ensure_user(TEST_TELEGRAM_ID)

    app.dependency_overrides[get_current_user] = _override_user
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value
    app.dependency_overrides.clear()


async def _seed_supporting_sessions(
    db_session,
    *,
    user_id,
    task_id,
    anchor: datetime,
) -> None:
    for days_ago in (1, 2):
        started_at = anchor - timedelta(days=days_ago)
        work_block = CalendarEvent(
            user_id=user_id,
            source=CalendarSource.INTERNAL,
            title=f"Fixture WorkBlock {days_ago}",
            start_at=started_at,
            end_at=started_at + timedelta(minutes=25),
            timezone="UTC",
            busy=True,
            status=CalendarEventStatus.CONFIRMED,
            created_by="fixture",
            source_task_id=task_id,
        )
        db_session.add(work_block)
        await db_session.flush()
        db_session.add(
            FocusSession(
                user_id=user_id,
                task_id=task_id,
                planned_event_id=work_block.id,
                intention=f"Fixture focus {days_ago}",
                planned_minutes=25,
                status=FocusSessionStatus.COMPLETED,
                started_at=started_at,
                target_end_at=started_at + timedelta(minutes=25),
                ended_at=started_at + timedelta(minutes=35),
                duration_seconds=35 * 60,
                focus_score=4,
            )
        )
    await db_session.flush()


async def test_product_v2_core_loop_is_coherent(
    client,
    db_session,
    monkeypatch,
):
    anchor = datetime(2035, 7, 11, 9, 0, tzinfo=UTC)
    clock = _Clock(anchor - timedelta(hours=1))
    for module in (
        "lumi.services.calendar",
        "lumi.services.focus",
        "lumi.services.focus_insights",
        "lumi.services.planning",
        "lumi.services.reflection_analysis",
        "lumi.services.work_blocks",
    ):
        monkeypatch.setattr(f"{module}.utc_now", clock.now)

    async def fake_enqueue(*_args, **_kwargs):
        return "reflection-job"

    monkeypatch.setattr(
        "lumi.services.reflection_analysis.enqueue_job",
        fake_enqueue,
    )
    reflection_extractor = _ReflectionExtractor()
    monkeypatch.setattr(
        "lumi.services.reflection_analysis.ReflectionExtractor",
        lambda: reflection_extractor,
    )
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID)
    user.timezone = "UTC"
    user.settings = {
        "planning": {
            "work_days": [0, 1, 2, 3, 4, 5, 6],
            "work_hours": {"start": "08:00", "end": "18:00"},
        }
    }
    await db_session.commit()

    captured = await client.post(
        "/api/tasks",
        json={"title": "Ship Product V2", "estimated_minutes": 25},
    )
    assert captured.status_code == 201
    task_id = uuid.UUID(captured.json()["task"]["id"])

    summary, proposed = await PlanningService(
        db_session,
        llm=_PlanGateway(task_id=str(task_id), start_at=anchor),
    ).propose_day_plan(
        user,
        mode="today",
        request_id="product-v2-loop",
    )
    assert summary.startswith("One safe block")
    assert len(proposed) == 1
    await db_session.commit()

    confirmed = await client.post(
        f"/api/calendar/blocks/{proposed[0].id}/confirm"
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["event"]["status"] == "confirmed"
    assert confirmed.json()["event"]["kind"] == "work_block"

    clock.value = anchor
    started = await client.post(
        "/api/focus/sessions",
        json={
            "planned_event_id": str(proposed[0].id),
            "intention": "Ship Product V2",
            "planned_minutes": 25,
            "break_minutes": 5,
        },
    )
    assert started.status_code == 201
    focus_session_id = uuid.UUID(started.json()["session"]["id"])
    assert started.json()["session"]["planned_event_id"] == str(proposed[0].id)

    clock.value = anchor + timedelta(minutes=35)
    finished = await client.post(
        f"/api/focus/sessions/{focus_session_id}/finish",
        json={
            "reflection_outcome": "progress",
            "reflection_text": (
                "Completed the integration loop. Next: owner dogfood."
            ),
            "accomplished_text": "Completed the integration loop",
            "next_step_text": "Run owner dogfood",
            "focus_score": 4,
        },
    )
    assert finished.status_code == 200
    session_payload = finished.json()["session"]
    assert session_payload["actual_minutes"] == 35
    assert session_payload["planned_vs_actual_minutes"] == 10
    assert session_payload["cycle"]["phase"] == "break"

    active_break = await client.get("/api/focus/state")
    assert active_break.status_code == 200
    assert active_break.json()["active_break"]["id"] == str(focus_session_id)

    analysis = await db_session.scalar(
        select(FocusSessionAnalysis).where(
            FocusSessionAnalysis.focus_session_id == focus_session_id
        )
    )
    assert analysis is not None
    processed = await ReflectionAnalysisService(
        db_session,
        extractor=reflection_extractor,
    ).process(user_id=user.id, analysis_id=analysis.id)
    assert processed is not None
    assert processed.status == FocusAnalysisStatus.READY
    await db_session.commit()

    clock.value = anchor + timedelta(minutes=40)
    ended_break = await client.post(
        f"/api/focus/sessions/{focus_session_id}/break/finish"
    )
    assert ended_break.status_code == 200
    assert ended_break.json()["session"]["cycle"]["phase"] == "done"
    assert ended_break.json()["session"]["actual_minutes"] == 35

    await _seed_supporting_sessions(
        db_session,
        user_id=user.id,
        task_id=task_id,
        anchor=anchor,
    )
    await db_session.commit()

    reviewed = await client.get(f"/api/focus/sessions/{focus_session_id}")
    assert reviewed.status_code == 200
    assert reviewed.json()["session"]["reflection"]["analysis"]["status"] == "ready"
    task = await db_session.get(Task, task_id, populate_existing=True)
    assert task is not None
    assert task.status.value == "inbox"

    insights = await client.get("/api/focus/insights?limit=3")
    assert insights.status_code == 200
    insight = next(
        item
        for item in insights.json()["items"]
        if item["kind"] == "planned_actual_gap"
    )
    assert insight["support_count"] == 3
    assert str(focus_session_id) in insight["evidence"]["supporting_session_ids"]
    assert "not a cause" in insight["statement"]

    tried = await client.post(f"/api/focus/insights/{insight['id']}/try")
    assert tried.status_code == 200
    assert tried.json()["insight"]["status"] == "confirmed"
