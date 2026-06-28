"""Focus timer sessions and lightweight analytics."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

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
    average_daily_focus_seconds: int
    average_daily_focus_delta_percent: int | None
    total_focus_delta_percent: int | None
    most_focused_daypart: str | None
    daypart_breakdown: list[dict]
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

    def period_bounds(
        self,
        user: User,
        period: str,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[datetime, datetime, int]:
        if period == "custom":
            if from_date is None or to_date is None or to_date < from_date:
                raise ValueError("invalid_focus_range")
            bucket_count = (to_date - from_date).days + 1
            if bucket_count > 180:
                raise ValueError("focus_range_too_large")
            zone = get_zone(user.timezone)
            start_local = datetime.combine(from_date, time.min, tzinfo=zone)
            end_local = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=zone)
            return start_local.astimezone(UTC), end_local.astimezone(UTC), bucket_count

        now = utc_now()
        today_start, today_end = local_day_bounds(now, user.timezone)
        if period == "month":
            zone = get_zone(user.timezone)
            local_now = now.astimezone(zone)
            local_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if local_start.month == 12:
                local_end = local_start.replace(year=local_start.year + 1, month=1)
            else:
                local_end = local_start.replace(month=local_start.month + 1)
            return local_start, local_end, (local_end.date() - local_start.date()).days
        return today_start - timedelta(days=6), today_end, 7

    async def list_sessions(
        self,
        user: User,
        *,
        period: str,
        limit: int = 100,
        offset: int = 0,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[list[FocusSession], bool, int | None]:
        start, end, _ = self.period_bounds(user, period, from_date=from_date, to_date=to_date)
        result = await self.session.execute(
            select(FocusSession)
            .where(
                FocusSession.user_id == user.id,
                FocusSession.status == FocusSessionStatus.COMPLETED,
                FocusSession.started_at >= start,
                FocusSession.started_at < end,
            )
            .order_by(FocusSession.started_at.desc())
            .offset(offset)
            .limit(limit + 1)
        )
        items = list(result.scalars())
        has_more = len(items) > limit
        page = items[:limit]
        return page, has_more, offset + limit if has_more else None

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

    async def update_completed_session(
        self,
        user: User,
        focus_session: FocusSession,
        *,
        intention: str | None = None,
        task_id: uuid.UUID | None = None,
        project: str | None = None,
        accomplished_text: str | None = None,
        distraction_text: str | None = None,
        next_step_text: str | None = None,
        focus_score: int | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> FocusSession:
        if focus_session.user_id != user.id or focus_session.status != FocusSessionStatus.COMPLETED:
            raise ValueError("focus_session_not_completed")
        task = await self.get_task(user, task_id) if task_id is not None else None
        if task_id is not None and task is None:
            raise ValueError("task_not_found")

        if intention is not None:
            focus_session.intention = intention.strip()[:300]
        if task_id is not None:
            focus_session.task_id = task.id
        if project is not None:
            cleaned_project = project.strip() or None
            focus_session.project_snapshot = cleaned_project or (task.project if task else None)
        if started_at is not None or ended_at is not None:
            next_started = started_at or focus_session.started_at
            next_ended = ended_at or focus_session.ended_at or focus_session.target_end_at
            if next_started.tzinfo is None:
                next_started = next_started.replace(tzinfo=get_zone(user.timezone))
            if next_ended.tzinfo is None:
                next_ended = next_ended.replace(tzinfo=get_zone(user.timezone))
            next_started = next_started.astimezone(UTC)
            next_ended = next_ended.astimezone(UTC)
            if next_ended <= next_started:
                raise ValueError("invalid_focus_session_time")
            focus_session.started_at = next_started
            focus_session.ended_at = next_ended
            focus_session.duration_seconds = int((next_ended - next_started).total_seconds())
        focus_session.accomplished_text = (accomplished_text or "").strip() or None
        focus_session.distraction_text = (distraction_text or "").strip() or None
        focus_session.next_step_text = (next_step_text or "").strip() or None
        focus_session.focus_score = focus_score
        await self.session.flush()
        return focus_session

    async def delete_session(self, user: User, focus_session: FocusSession) -> None:
        if focus_session.user_id != user.id:
            raise ValueError("focus_session_not_found")
        if focus_session.status == FocusSessionStatus.ACTIVE:
            raise ValueError("focus_session_active")
        await self.session.delete(focus_session)
        await self.session.flush()

    async def log_session(
        self,
        user: User,
        *,
        intention: str,
        logged_at: datetime,
        duration_minutes: int,
        task_id: uuid.UUID | None = None,
        project: str | None = None,
        accomplished_text: str | None = None,
        distraction_text: str | None = None,
        next_step_text: str | None = None,
        focus_score: int | None = None,
    ) -> FocusSession:
        task = await self.get_task(user, task_id)
        if task_id is not None and task is None:
            raise ValueError("task_not_found")

        started = logged_at if logged_at.tzinfo else logged_at.replace(tzinfo=get_zone(user.timezone))
        ended = started + timedelta(minutes=duration_minutes)
        cleaned_project = (project or "").strip() or None
        focus_session = FocusSession(
            user_id=user.id,
            task_id=task.id if task else None,
            project_snapshot=cleaned_project or (task.project if task else None),
            intention=intention.strip()[:300],
            planned_minutes=duration_minutes,
            status=FocusSessionStatus.COMPLETED,
            started_at=started,
            target_end_at=ended,
            ended_at=ended,
            duration_seconds=duration_minutes * 60,
            accomplished_text=(accomplished_text or "").strip() or None,
            distraction_text=(distraction_text or "").strip() or None,
            next_step_text=(next_step_text or "").strip() or None,
            focus_score=focus_score,
        )
        self.session.add(focus_session)
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

    async def completed_seconds_between(self, user: User, start: datetime, end: datetime) -> int:
        sessions = await self.completed_between(user, start, end)
        return sum(item.duration_seconds or 0 for item in sessions)

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

    async def summary(
        self,
        user: User,
        *,
        period: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> FocusSummary:
        if period not in {"month", "custom"}:
            period = "week"
        start, end, bucket_count = self.period_bounds(user, period, from_date=from_date, to_date=to_date)
        sessions = await self.completed_between(user, start, end)

        zone = get_zone(user.timezone)
        start_local_date = start.astimezone(zone).date()
        by_project: dict[str, dict] = defaultdict(lambda: {"focus_seconds": 0, "session_count": 0})
        by_day = {
            i: {
                "date": (start_local_date + timedelta(days=i)).isoformat(),
                "focus_seconds": 0,
                "session_count": 0,
                "_scores": [],
            }
            for i in range(bucket_count)
        }
        scores: list[int] = []
        next_steps: list[str] = []
        by_daypart: dict[str, int] = {"morning": 0, "afternoon": 0, "evening": 0, "night": 0}

        for item in sessions:
            seconds = item.duration_seconds or 0
            project = item.project_snapshot or "Без проекта"
            by_project[project]["focus_seconds"] += seconds
            by_project[project]["session_count"] += 1
            hour = item.started_at.astimezone(zone).hour
            if 6 <= hour < 12:
                daypart = "morning"
            elif 12 <= hour < 18:
                daypart = "afternoon"
            elif 18 <= hour < 24:
                daypart = "evening"
            else:
                daypart = "night"
            by_daypart[daypart] += seconds

            day_index = (item.started_at.astimezone(zone).date() - start_local_date).days
            if day_index in by_day:
                by_day[day_index]["focus_seconds"] += seconds
                by_day[day_index]["session_count"] += 1
                if item.focus_score is not None:
                    by_day[day_index]["_scores"].append(item.focus_score)
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
        baseline_start = start - timedelta(days=bucket_count * 4)
        baseline_total = await self.completed_seconds_between(user, baseline_start, start)
        baseline_period_average = baseline_total / 4 if baseline_total else 0
        baseline_daily_average = baseline_total / (bucket_count * 4) if baseline_total else 0
        average_daily = round(total_seconds / bucket_count)
        total_delta = (
            round(((total_seconds - baseline_period_average) / baseline_period_average) * 100)
            if baseline_period_average
            else None
        )
        average_daily_delta = (
            round(((average_daily - baseline_daily_average) / baseline_daily_average) * 100)
            if baseline_daily_average
            else None
        )
        daypart_breakdown = [
            {"daypart": daypart, "focus_seconds": seconds}
            for daypart, seconds in sorted(by_daypart.items(), key=lambda item: (-item[1], item[0]))
        ]
        most_focused_daypart = daypart_breakdown[0]["daypart"] if daypart_breakdown and daypart_breakdown[0]["focus_seconds"] else None
        avg_score = round(sum(scores) / len(scores), 1) if scores else None
        daily_activity = []
        for values in by_day.values():
            day_scores = values.pop("_scores")
            daily_activity.append(
                {
                    **values,
                    "average_focus_score": round(sum(day_scores) / len(day_scores), 1) if day_scores else None,
                }
            )
        return FocusSummary(
            period=period,
            total_focus_seconds=total_seconds,
            total_sessions=len(sessions),
            streak_days=await self.streak_days(user),
            average_focus_score=avg_score,
            average_daily_focus_seconds=average_daily,
            average_daily_focus_delta_percent=average_daily_delta,
            total_focus_delta_percent=total_delta,
            most_focused_daypart=most_focused_daypart,
            daypart_breakdown=daypart_breakdown,
            daily_activity=daily_activity,
            project_breakdown=breakdown,
            next_steps=next_steps[:5],
        )
