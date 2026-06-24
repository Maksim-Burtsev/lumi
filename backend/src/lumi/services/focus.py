"""Focus timer sessions and lightweight analytics."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import FocusSession, FocusSessionStatus, Task, User
from lumi.utils.time import get_zone, local_day_bounds, utc_now


@dataclass(slots=True)
class FocusSummary:
    period: str
    total_focus_seconds: int
    total_sessions: int
    streak_days: int
    average_focus_score: float | None
    daily_activity: list[dict]
    project_breakdown: list[dict]
    next_steps: list[str]


class FocusService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_task(self, user: User, task_id: uuid.UUID | None) -> Task | None:
        if task_id is None:
            return None
        result = await self.session.execute(
            select(Task).where(Task.id == task_id, Task.user_id == user.id)
        )
        return result.scalar_one_or_none()

    async def get_active(self, user: User) -> FocusSession | None:
        result = await self.session.execute(
            select(FocusSession)
            .where(
                FocusSession.user_id == user.id,
                FocusSession.status == FocusSessionStatus.ACTIVE,
            )
            .order_by(FocusSession.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def start_session(
        self,
        user: User,
        *,
        intention: str,
        planned_minutes: int,
        task_id: uuid.UUID | None = None,
        project: str | None = None,
    ) -> FocusSession:
        if await self.get_active(user) is not None:
            raise ValueError("active_focus_session_exists")
        task = await self.get_task(user, task_id)
        if task_id is not None and task is None:
            raise ValueError("task_not_found")

        now = utc_now()
        cleaned_project = (project or "").strip() or None
        focus_session = FocusSession(
            user_id=user.id,
            task_id=task.id if task else None,
            project_snapshot=cleaned_project or (task.project if task else None),
            intention=intention.strip()[:300],
            planned_minutes=planned_minutes,
            status=FocusSessionStatus.ACTIVE,
            started_at=now,
            target_end_at=now + timedelta(minutes=planned_minutes),
        )
        self.session.add(focus_session)
        await self.session.flush()
        return focus_session

    async def get_session(self, user: User, session_id: uuid.UUID) -> FocusSession | None:
        result = await self.session.execute(
            select(FocusSession).where(FocusSession.id == session_id, FocusSession.user_id == user.id)
        )
        return result.scalar_one_or_none()

    async def finish_session(
        self,
        user: User,
        focus_session: FocusSession,
        *,
        ended_at: datetime | None,
        accomplished_text: str | None,
        distraction_text: str | None,
        next_step_text: str | None,
        focus_score: int | None,
    ) -> FocusSession:
        if focus_session.user_id != user.id or focus_session.status != FocusSessionStatus.ACTIVE:
            raise ValueError("focus_session_not_active")
        ended = ended_at or utc_now()
        if ended.tzinfo is None:
            ended = ended.replace(tzinfo=focus_session.started_at.tzinfo)
        focus_session.status = FocusSessionStatus.COMPLETED
        focus_session.ended_at = ended
        focus_session.duration_seconds = max(0, int((ended - focus_session.started_at).total_seconds()))
        focus_session.accomplished_text = (accomplished_text or "").strip() or None
        focus_session.distraction_text = (distraction_text or "").strip() or None
        focus_session.next_step_text = (next_step_text or "").strip() or None
        focus_session.focus_score = focus_score
        await self.session.flush()
        return focus_session

    async def abandon_session(self, user: User, focus_session: FocusSession) -> FocusSession:
        if focus_session.user_id != user.id or focus_session.status != FocusSessionStatus.ACTIVE:
            raise ValueError("focus_session_not_active")
        ended = utc_now()
        focus_session.status = FocusSessionStatus.ABANDONED
        focus_session.ended_at = ended
        focus_session.duration_seconds = max(0, int((ended - focus_session.started_at).total_seconds()))
        await self.session.flush()
        return focus_session

    async def recent_sessions(self, user: User, *, limit: int = 10) -> list[FocusSession]:
        result = await self.session.execute(
            select(FocusSession)
            .where(FocusSession.user_id == user.id, FocusSession.status == FocusSessionStatus.COMPLETED)
            .order_by(FocusSession.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def completed_between(self, user: User, start: datetime, end: datetime) -> list[FocusSession]:
        result = await self.session.execute(
            select(FocusSession)
            .where(
                FocusSession.user_id == user.id,
                FocusSession.status == FocusSessionStatus.COMPLETED,
                FocusSession.started_at >= start,
                FocusSession.started_at < end,
            )
            .order_by(FocusSession.started_at.asc())
        )
        return list(result.scalars())

    async def today_totals(self, user: User) -> dict:
        start, end = local_day_bounds(utc_now(), user.timezone)
        sessions = await self.completed_between(user, start, end)
        return {
            "focus_seconds": sum(item.duration_seconds or 0 for item in sessions),
            "completed_sessions": len(sessions),
            "streak_days": await self.streak_days(user),
        }

    async def streak_days(self, user: User) -> int:
        zone = get_zone(user.timezone)
        local_today = utc_now().astimezone(zone).date()
        start, _ = local_day_bounds(utc_now() - timedelta(days=180), user.timezone)
        result = await self.session.execute(
            select(FocusSession.started_at)
            .where(
                FocusSession.user_id == user.id,
                FocusSession.status == FocusSessionStatus.COMPLETED,
                FocusSession.started_at >= start,
            )
        )
        days = {dt.astimezone(zone).date() for dt in result.scalars()}
        streak = 0
        cursor = local_today
        while cursor in days:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    async def summary(self, user: User, *, period: str) -> FocusSummary:
        now = utc_now()
        today_start, today_end = local_day_bounds(now, user.timezone)
        if period == "month":
            start = today_start - timedelta(days=29)
            bucket_count = 30
        else:
            period = "week"
            start = today_start - timedelta(days=6)
            bucket_count = 7
        sessions = await self.completed_between(user, start, today_end)

        zone = get_zone(user.timezone)
        start_local_date = start.astimezone(zone).date()
        by_project: dict[str, dict] = defaultdict(lambda: {"focus_seconds": 0, "session_count": 0})
        by_day = {
            i: {
                "date": (start_local_date + timedelta(days=i)).isoformat(),
                "focus_seconds": 0,
                "session_count": 0,
            }
            for i in range(bucket_count)
        }
        scores: list[int] = []
        next_steps: list[str] = []

        for item in sessions:
            seconds = item.duration_seconds or 0
            project = item.project_snapshot or "Без проекта"
            by_project[project]["focus_seconds"] += seconds
            by_project[project]["session_count"] += 1

            day_index = (item.started_at.astimezone(zone).date() - start_local_date).days
            if day_index in by_day:
                by_day[day_index]["focus_seconds"] += seconds
                by_day[day_index]["session_count"] += 1
            if item.focus_score is not None:
                scores.append(item.focus_score)
            if item.next_step_text:
                next_steps.append(item.next_step_text)

        breakdown = [
            {"project": project, **values}
            for project, values in sorted(
                by_project.items(),
                key=lambda pair: (-pair[1]["focus_seconds"], pair[0].lower()),
            )
        ]
        total_seconds = sum(item.duration_seconds or 0 for item in sessions)
        avg_score = round(sum(scores) / len(scores), 1) if scores else None
        return FocusSummary(
            period=period,
            total_focus_seconds=total_seconds,
            total_sessions=len(sessions),
            streak_days=await self.streak_days(user),
            average_focus_score=avg_score,
            daily_activity=list(by_day.values()),
            project_breakdown=breakdown,
            next_steps=next_steps[:5],
        )
