"""Focus timer sessions and lightweight analytics."""

from __future__ import annotations

import calendar
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import FocusSession, FocusSessionStatus, Project, Task, User
from lumi.services.projects import ProjectService
from lumi.services.realtime import RealtimeEventService
from lumi.utils.time import get_zone, local_day_bounds, utc_now

MAX_EDIT_DURATION = timedelta(hours=24)
FUTURE_TOLERANCE = timedelta(minutes=5)
UNSET = object()


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


def _clean_text(value: str | None) -> str | None:
    return (value or "").strip() or None


class FocusService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_task(self, user: User, task_id: uuid.UUID | None) -> Task | None:
        if task_id is None:
            return None
        result = await self.session.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
        return result.scalar_one_or_none()

    async def get_active(self, user: User) -> FocusSession | None:
        result = await self.session.execute(
            select(FocusSession)
            .where(
                FocusSession.user_id == user.id,
                FocusSession.status == FocusSessionStatus.ACTIVE,
            )
            .order_by(FocusSession.started_at.desc(), FocusSession.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _resolve_project(
        self,
        user: User,
        *,
        task: Task | None,
        project_id: uuid.UUID | None | object = UNSET,
        project_name: str | None | object = UNSET,
    ) -> Project | None:
        project_service = ProjectService(self.session)

        if project_id is not UNSET and project_id is not None:
            assert isinstance(project_id, uuid.UUID)
            project = await project_service.get(user, project_id)
            if project is None:
                raise ValueError("project_not_found")
            supplied_name = _clean_text(project_name) if isinstance(project_name, str) else None
            if supplied_name and supplied_name.casefold() != project.name.casefold():
                raise ValueError("project_mismatch")
            return project

        if project_name is not UNSET:
            if project_name is None:
                return None
            assert isinstance(project_name, str)
            return await project_service.get_or_create(user, project_name)

        if project_id is not UNSET:
            # Explicit project_id=null means intentionally unassigned, even when a task is set.
            return None

        if task is None:
            return None
        if task.project_id is not None:
            project = await project_service.get(user, task.project_id)
            if project is not None:
                return project
        return await project_service.get_or_create(user, task.project)

    async def _emit(self, focus_session: FocusSession, event_type: str) -> None:
        await RealtimeEventService(self.session).emit(
            user_id=focus_session.user_id,
            topics=["focus"],
            event_type=event_type,
            payload={"session_id": str(focus_session.id)},
        )

    async def start_session(
        self,
        user: User,
        *,
        intention: str,
        planned_minutes: int,
        task_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None | object = UNSET,
        project_name: str | None | object = UNSET,
    ) -> FocusSession:
        clean_intention = _clean_text(intention)
        if clean_intention is None:
            raise ValueError("invalid_focus_intention")
        # Serialize starts per user before resolving/creating a project. The partial
        # unique index remains the final safeguard, but this also makes custom-project
        # creation deterministic under two simultaneous starts.
        await self.session.execute(select(User.id).where(User.id == user.id).with_for_update())
        if await self.get_active(user) is not None:
            raise ValueError("active_focus_session_exists")
        task = await self.get_task(user, task_id)
        if task_id is not None and task is None:
            raise ValueError("task_not_found")
        project = await self._resolve_project(
            user,
            task=task,
            project_id=project_id,
            project_name=project_name,
        )

        now = utc_now()
        focus_session = FocusSession(
            user_id=user.id,
            task_id=task.id if task else None,
            project_id=project.id if project else None,
            project_snapshot=project.name if project else None,
            intention=clean_intention[:300],
            planned_minutes=planned_minutes,
            status=FocusSessionStatus.ACTIVE,
            started_at=now,
            target_end_at=now + timedelta(minutes=planned_minutes),
        )
        try:
            async with self.session.begin_nested():
                self.session.add(focus_session)
                await self.session.flush()
        except IntegrityError as exc:
            raise ValueError("active_focus_session_exists") from exc
        await self._emit(focus_session, "focus.started")
        return focus_session

    async def get_session(self, user: User, session_id: uuid.UUID) -> FocusSession | None:
        result = await self.session.execute(
            select(FocusSession).where(
                FocusSession.id == session_id,
                FocusSession.user_id == user.id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_locked_session(
        self,
        user: User,
        session_id: uuid.UUID,
    ) -> FocusSession | None:
        result = await self.session.execute(
            select(FocusSession)
            .where(
                FocusSession.id == session_id,
                FocusSession.user_id == user.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def related_entities(
        self,
        user: User,
        sessions: list[FocusSession],
    ) -> tuple[dict[uuid.UUID, Task], dict[uuid.UUID, Project]]:
        task_ids = {item.task_id for item in sessions if item.task_id is not None}
        project_ids = {item.project_id for item in sessions if item.project_id is not None}
        tasks: dict[uuid.UUID, Task] = {}
        projects: dict[uuid.UUID, Project] = {}
        if task_ids:
            task_result = await self.session.execute(
                select(Task).where(Task.user_id == user.id, Task.id.in_(task_ids))
            )
            tasks = {item.id: item for item in task_result.scalars()}
        if project_ids:
            project_result = await self.session.execute(
                select(Project).where(Project.user_id == user.id, Project.id.in_(project_ids))
            )
            projects = {item.id: item for item in project_result.scalars()}
        return tasks, projects

    @staticmethod
    def _date_bounds(user: User, start_date: date, end_date: date) -> tuple[datetime, datetime]:
        zone = get_zone(user.timezone)
        start = datetime.combine(start_date, time.min, tzinfo=zone).astimezone(UTC)
        end = datetime.combine(end_date, time.min, tzinfo=zone).astimezone(UTC)
        return start, end

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
            start, end = self._date_bounds(user, from_date, to_date + timedelta(days=1))
            return start, end, bucket_count

        local_today = utc_now().astimezone(get_zone(user.timezone)).date()
        if period == "month":
            month_start = local_today.replace(day=1)
            if month_start.month == 12:
                month_end = date(month_start.year + 1, 1, 1)
            else:
                month_end = date(month_start.year, month_start.month + 1, 1)
            # Keep all month buckets for the chart, but aggregate only elapsed local days.
            start, end = self._date_bounds(user, month_start, local_today + timedelta(days=1))
            return start, end, (month_end - month_start).days

        start_date = local_today - timedelta(days=6)
        start, end = self._date_bounds(user, start_date, local_today + timedelta(days=1))
        return start, end, 7

    @staticmethod
    def _completed_sessions_stmt(
        user: User,
        start: datetime,
        end: datetime,
        *,
        q: str | None = None,
        project_id: uuid.UUID | None = None,
    ) -> Select[tuple[FocusSession]]:
        """Build the ownership-scoped query shared by History and its analytics."""
        stmt = (
            select(FocusSession)
            .outerjoin(
                Task,
                and_(Task.id == FocusSession.task_id, Task.user_id == user.id),
            )
            .outerjoin(
                Project,
                and_(Project.id == FocusSession.project_id, Project.user_id == user.id),
            )
            .where(
                FocusSession.user_id == user.id,
                FocusSession.status == FocusSessionStatus.COMPLETED,
                FocusSession.started_at >= start,
                FocusSession.started_at < end,
            )
        )
        if project_id is not None:
            stmt = stmt.where(
                FocusSession.project_id == project_id,
                Project.id.is_not(None),
            )
        search = _clean_text(q)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    FocusSession.intention.ilike(pattern),
                    FocusSession.accomplished_text.ilike(pattern),
                    FocusSession.distraction_text.ilike(pattern),
                    FocusSession.next_step_text.ilike(pattern),
                    FocusSession.project_snapshot.ilike(pattern),
                    Project.name.ilike(pattern),
                    Task.title.ilike(pattern),
                )
            )
        return stmt

    async def list_sessions(
        self,
        user: User,
        *,
        period: str,
        limit: int = 100,
        offset: int = 0,
        from_date: date | None = None,
        to_date: date | None = None,
        q: str | None = None,
        project_id: uuid.UUID | None = None,
    ) -> tuple[list[FocusSession], bool, int | None]:
        start, end, _ = self.period_bounds(user, period, from_date=from_date, to_date=to_date)
        stmt = self._completed_sessions_stmt(
            user,
            start,
            end,
            q=q,
            project_id=project_id,
        )
        result = await self.session.execute(
            stmt.order_by(FocusSession.started_at.desc(), FocusSession.id.desc())
            .offset(offset)
            .limit(limit + 1)
        )
        items = list(result.scalars())
        has_more = len(items) > limit
        page = items[:limit]
        return page, has_more, offset + len(page) if has_more else None

    @staticmethod
    def _normalize_timestamp(user: User, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=get_zone(user.timezone))
        return value.astimezone(UTC)

    def _validate_manual_range(self, user: User, started_at: datetime, ended_at: datetime) -> None:
        if ended_at <= started_at:
            raise ValueError("invalid_focus_session_time")
        if ended_at - started_at > MAX_EDIT_DURATION:
            raise ValueError("focus_session_duration_too_long")
        if ended_at > utc_now() + FUTURE_TOLERANCE:
            raise ValueError("focus_session_time_in_future")

    async def finish_session(
        self,
        user: User,
        focus_session: FocusSession,
        *,
        accomplished_text: str | None,
        distraction_text: str | None,
        next_step_text: str | None,
        focus_score: int | None,
    ) -> FocusSession:
        locked = await self._get_locked_session(user, focus_session.id)
        if locked is None:
            raise ValueError("focus_session_not_found")
        if locked.status != FocusSessionStatus.ACTIVE:
            raise ValueError("focus_session_not_active")
        ended = utc_now()
        if ended <= locked.started_at:
            raise ValueError("invalid_focus_session_time")
        locked.status = FocusSessionStatus.COMPLETED
        locked.ended_at = ended
        locked.duration_seconds = int((ended - locked.started_at).total_seconds())
        locked.accomplished_text = _clean_text(accomplished_text)
        locked.distraction_text = _clean_text(distraction_text)
        locked.next_step_text = _clean_text(next_step_text)
        locked.focus_score = focus_score
        await self.session.flush()
        await self._emit(locked, "focus.finished")
        return locked

    async def update_completed_session(
        self,
        user: User,
        focus_session: FocusSession,
        *,
        updates: dict[str, Any],
    ) -> FocusSession:
        locked = await self._get_locked_session(user, focus_session.id)
        if locked is None:
            raise ValueError("focus_session_not_found")
        if locked.status != FocusSessionStatus.COMPLETED:
            raise ValueError("focus_session_not_completed")

        task: Task | None = None
        if "task_id" in updates:
            task_id = updates["task_id"]
            task = await self.get_task(user, task_id)
            if task_id is not None and task is None:
                raise ValueError("task_not_found")
            locked.task_id = task.id if task else None

        if "project_id" in updates or "project_name" in updates:
            project = await self._resolve_project(
                user,
                task=task,
                project_id=updates.get("project_id", UNSET),
                project_name=updates.get("project_name", UNSET),
            )
            locked.project_id = project.id if project else None
            locked.project_snapshot = project.name if project else None

        if "intention" in updates:
            intention = _clean_text(updates["intention"])
            if intention is None:
                raise ValueError("invalid_focus_intention")
            locked.intention = intention[:300]

        if "started_at" in updates or "ended_at" in updates:
            started_value = updates.get("started_at", locked.started_at)
            ended_value = updates.get("ended_at", locked.ended_at)
            if started_value is None or ended_value is None:
                raise ValueError("invalid_focus_session_time")
            next_started = self._normalize_timestamp(user, started_value)
            next_ended = self._normalize_timestamp(user, ended_value)
            self._validate_manual_range(user, next_started, next_ended)
            locked.started_at = next_started
            locked.ended_at = next_ended
            locked.target_end_at = next_ended
            locked.planned_minutes = max(1, min(240, round((next_ended - next_started).total_seconds() / 60)))
            locked.duration_seconds = int((next_ended - next_started).total_seconds())

        for field in ("accomplished_text", "distraction_text", "next_step_text"):
            if field in updates:
                setattr(locked, field, _clean_text(updates[field]))
        if "focus_score" in updates:
            locked.focus_score = updates["focus_score"]

        await self.session.flush()
        await self._emit(locked, "focus.updated")
        return locked

    async def delete_session(self, user: User, focus_session: FocusSession) -> None:
        locked = await self._get_locked_session(user, focus_session.id)
        if locked is None:
            raise ValueError("focus_session_not_found")
        if locked.status == FocusSessionStatus.ACTIVE:
            raise ValueError("focus_session_active")
        session_id = locked.id
        await self.session.delete(locked)
        await self.session.flush()
        await RealtimeEventService(self.session).emit(
            user_id=user.id,
            topics=["focus"],
            event_type="focus.deleted",
            payload={"session_id": str(session_id)},
        )

    async def log_session(
        self,
        user: User,
        *,
        intention: str,
        logged_at: datetime,
        duration_minutes: int,
        task_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None | object = UNSET,
        project_name: str | None | object = UNSET,
        accomplished_text: str | None = None,
        distraction_text: str | None = None,
        next_step_text: str | None = None,
        focus_score: int | None = None,
    ) -> FocusSession:
        clean_intention = _clean_text(intention)
        if clean_intention is None:
            raise ValueError("invalid_focus_intention")
        task = await self.get_task(user, task_id)
        if task_id is not None and task is None:
            raise ValueError("task_not_found")
        project = await self._resolve_project(
            user,
            task=task,
            project_id=project_id,
            project_name=project_name,
        )
        started = self._normalize_timestamp(user, logged_at)
        ended = started + timedelta(minutes=duration_minutes)
        self._validate_manual_range(user, started, ended)
        focus_session = FocusSession(
            user_id=user.id,
            task_id=task.id if task else None,
            project_id=project.id if project else None,
            project_snapshot=project.name if project else None,
            intention=clean_intention[:300],
            planned_minutes=duration_minutes,
            status=FocusSessionStatus.COMPLETED,
            started_at=started,
            target_end_at=ended,
            ended_at=ended,
            duration_seconds=duration_minutes * 60,
            accomplished_text=_clean_text(accomplished_text),
            distraction_text=_clean_text(distraction_text),
            next_step_text=_clean_text(next_step_text),
            focus_score=focus_score,
        )
        self.session.add(focus_session)
        await self.session.flush()
        await self._emit(focus_session, "focus.logged")
        return focus_session

    async def abandon_session(self, user: User, focus_session: FocusSession) -> FocusSession:
        locked = await self._get_locked_session(user, focus_session.id)
        if locked is None:
            raise ValueError("focus_session_not_found")
        if locked.status != FocusSessionStatus.ACTIVE:
            raise ValueError("focus_session_not_active")
        ended = utc_now()
        if ended <= locked.started_at:
            raise ValueError("invalid_focus_session_time")
        locked.status = FocusSessionStatus.ABANDONED
        locked.ended_at = ended
        locked.duration_seconds = int((ended - locked.started_at).total_seconds())
        await self.session.flush()
        await self._emit(locked, "focus.abandoned")
        return locked

    async def recent_sessions(self, user: User, *, limit: int = 10) -> list[FocusSession]:
        result = await self.session.execute(
            select(FocusSession)
            .where(
                FocusSession.user_id == user.id,
                FocusSession.status == FocusSessionStatus.COMPLETED,
            )
            .order_by(FocusSession.started_at.desc(), FocusSession.id.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def completed_between(
        self,
        user: User,
        start: datetime,
        end: datetime,
        *,
        q: str | None = None,
        project_id: uuid.UUID | None = None,
    ) -> list[FocusSession]:
        result = await self.session.execute(
            self._completed_sessions_stmt(
                user,
                start,
                end,
                q=q,
                project_id=project_id,
            ).order_by(FocusSession.started_at.asc(), FocusSession.id.asc())
        )
        return list(result.scalars())

    async def completed_seconds_between(
        self,
        user: User,
        start: datetime,
        end: datetime,
        *,
        q: str | None = None,
        project_id: uuid.UUID | None = None,
    ) -> int:
        sessions = await self.completed_between(
            user,
            start,
            end,
            q=q,
            project_id=project_id,
        )
        return sum(item.duration_seconds or 0 for item in sessions)

    async def today_totals(self, user: User) -> dict:
        start, end = local_day_bounds(utc_now(), user.timezone)
        sessions = await self.completed_between(user, start, end)
        return {
            "focus_seconds": sum(item.duration_seconds or 0 for item in sessions),
            "completed_sessions": len(sessions),
            "streak_days": await self.streak_days(user),
        }

    async def streak_days(
        self,
        user: User,
        *,
        q: str | None = None,
        project_id: uuid.UUID | None = None,
    ) -> int:
        zone = get_zone(user.timezone)
        local_today = utc_now().astimezone(zone).date()
        start, end = self._date_bounds(
            user,
            local_today - timedelta(days=180),
            local_today + timedelta(days=1),
        )
        result = await self.session.execute(
            self._completed_sessions_stmt(
                user,
                start,
                end,
                q=q,
                project_id=project_id,
            ).with_only_columns(FocusSession.started_at)
        )
        days = {dt.astimezone(zone).date() for dt in result.scalars()}
        streak = 0
        cursor = local_today
        while cursor in days:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    @staticmethod
    def _shift_month(month_start: date, months: int) -> date:
        month_index = month_start.year * 12 + month_start.month - 1 + months
        return date(month_index // 12, month_index % 12 + 1, 1)

    async def _baseline_totals(
        self,
        user: User,
        *,
        period: str,
        start_local_date: date,
        elapsed_days: int,
        q: str | None = None,
        project_id: uuid.UUID | None = None,
    ) -> list[int]:
        if period == "custom":
            return []
        totals: list[int] = []
        if period == "week":
            for index in range(1, 5):
                window_end = start_local_date - timedelta(days=(index - 1) * 7)
                window_start = window_end - timedelta(days=7)
                start, end = self._date_bounds(user, window_start, window_end)
                totals.append(
                    await self.completed_seconds_between(
                        user,
                        start,
                        end,
                        q=q,
                        project_id=project_id,
                    )
                )
            return totals

        for index in range(1, 5):
            month_start = self._shift_month(start_local_date, -index)
            days = min(elapsed_days, calendar.monthrange(month_start.year, month_start.month)[1])
            start, end = self._date_bounds(
                user,
                month_start,
                month_start + timedelta(days=days),
            )
            totals.append(
                await self.completed_seconds_between(
                    user,
                    start,
                    end,
                    q=q,
                    project_id=project_id,
                )
            )
        return totals

    async def summary(
        self,
        user: User,
        *,
        period: str,
        from_date: date | None = None,
        to_date: date | None = None,
        q: str | None = None,
        project_id: uuid.UUID | None = None,
    ) -> FocusSummary:
        if period not in {"month", "custom"}:
            period = "week"
        start, end, bucket_count = self.period_bounds(
            user,
            period,
            from_date=from_date,
            to_date=to_date,
        )
        sessions = await self.completed_between(
            user,
            start,
            end,
            q=q,
            project_id=project_id,
        )

        zone = get_zone(user.timezone)
        local_today = utc_now().astimezone(zone).date()
        start_local_date = start.astimezone(zone).date()
        elapsed_days = local_today.day if period == "month" else bucket_count
        by_project: dict[tuple[uuid.UUID | None, str | None], dict[str, int]] = defaultdict(
            lambda: {"focus_seconds": 0, "session_count": 0}
        )
        by_day: dict[int, dict[str, Any]] = {
            index: {
                "date": (start_local_date + timedelta(days=index)).isoformat(),
                "focus_seconds": 0,
                "session_count": 0,
                "_scores": [],
            }
            for index in range(bucket_count)
        }
        scores: list[int] = []
        next_steps: list[str] = []
        by_daypart: dict[str, int] = {
            "morning": 0,
            "afternoon": 0,
            "evening": 0,
            "night": 0,
        }
        _, projects = await self.related_entities(user, sessions)

        for item in sessions:
            seconds = item.duration_seconds or 0
            project = projects.get(item.project_id) if item.project_id else None
            project_name = project.name if project else item.project_snapshot
            project_key = (item.project_id, project_name)
            by_project[project_key]["focus_seconds"] += seconds
            by_project[project_key]["session_count"] += 1
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
            {
                "project_id": str(project_id) if project_id else None,
                "project_name": project_name,
                # Transitional alias; new clients use project_name.
                "project": project_name,
                **values,
            }
            for (project_id, project_name), values in sorted(
                by_project.items(),
                key=lambda pair: (
                    -pair[1]["focus_seconds"],
                    (pair[0][1] or "").casefold(),
                ),
            )
        ]
        total_seconds = sum(item.duration_seconds or 0 for item in sessions)
        baseline_totals = await self._baseline_totals(
            user,
            period=period,
            start_local_date=start_local_date,
            elapsed_days=elapsed_days,
            q=q,
            project_id=project_id,
        )
        baseline_period_average = sum(baseline_totals) / 4 if any(baseline_totals) else 0
        baseline_daily_average = (
            sum(baseline_totals) / (4 * elapsed_days) if any(baseline_totals) and elapsed_days else 0
        )
        average_daily = round(total_seconds / elapsed_days) if elapsed_days else 0
        total_delta = (
            round(((total_seconds - baseline_period_average) / baseline_period_average) * 100)
            if baseline_period_average and period != "custom"
            else None
        )
        average_daily_delta = (
            round(((average_daily - baseline_daily_average) / baseline_daily_average) * 100)
            if baseline_daily_average and period != "custom"
            else None
        )
        daypart_breakdown: list[dict[str, Any]] = [
            {"daypart": daypart, "focus_seconds": seconds}
            for daypart, seconds in sorted(by_daypart.items(), key=lambda item: (-item[1], item[0]))
        ]
        most_focused_daypart: str | None = (
            str(daypart_breakdown[0]["daypart"])
            if daypart_breakdown and daypart_breakdown[0]["focus_seconds"]
            else None
        )
        average_score = round(sum(scores) / len(scores), 1) if scores else None
        daily_activity = []
        for values in by_day.values():
            day_scores = values.pop("_scores")
            daily_activity.append(
                {
                    **values,
                    "average_focus_score": (
                        round(sum(day_scores) / len(day_scores), 1) if day_scores else None
                    ),
                }
            )
        return FocusSummary(
            period=period,
            total_focus_seconds=total_seconds,
            total_sessions=len(sessions),
            streak_days=await self.streak_days(user, q=q, project_id=project_id),
            average_focus_score=average_score,
            average_daily_focus_seconds=average_daily,
            average_daily_focus_delta_percent=average_daily_delta,
            total_focus_delta_percent=total_delta,
            most_focused_daypart=most_focused_daypart,
            daypart_breakdown=daypart_breakdown,
            daily_activity=daily_activity,
            project_breakdown=breakdown,
            next_steps=next_steps[:5],
        )
