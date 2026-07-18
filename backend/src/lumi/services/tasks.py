"""TaskService: create/complete/snooze tasks, reminders, audit trail."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from difflib import SequenceMatcher
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.schemas import ExtractedTask
from lumi.db.models import Priority, Project, Task, TaskEvent, TaskStatus, User
from lumi.services.assistant_suggestions import AssistantSuggestionService
from lumi.services.audit import AuditService
from lumi.services.projects import ProjectService
from lumi.services.realtime import RealtimeEventService
from lumi.utils.text import keyword_overlap, normalize_for_match
from lumi.utils.time import get_zone, local_day_bounds, local_to_utc, utc_now

SNOOZE_PRESETS = {"1h": timedelta(hours=1), "3h": timedelta(hours=3)}
RENAME_FUZZY_MIN_SCORE = 0.58
RENAME_FUZZY_CLEAR_MARGIN = 0.16
RENAME_MAX_CANDIDATES = 5
TaskBucket = Literal["inbox", "this_week", "later", "done"]
COMPLETED_FROM_STATUS_KEY = "completed_from_status"


@dataclass(slots=True)
class RenameTaskResult:
    status: Literal["renamed", "not_found", "ambiguous"]
    task: Task | None = None
    old_title: str | None = None
    new_title: str | None = None
    candidates: list[Task] = field(default_factory=list)


@dataclass(slots=True)
class _ScoredRenameCandidate:
    task: Task
    score: float
    index: int


def _task_snapshot(task: Task) -> dict[str, Any]:
    return {
        "title": task.title,
        "description": task.description,
        "status": task.status.value if isinstance(task.status, TaskStatus) else task.status,
        "priority": task.priority.value if isinstance(task.priority, Priority) else task.priority,
        "project": task.project,
        "project_id": str(task.project_id) if task.project_id else None,
        "tags": task.tags or [],
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "target_at": task.target_at.isoformat() if task.target_at else None,
        "reminder_at": task.reminder_at.isoformat() if task.reminder_at else None,
        "snoozed_until": task.snoozed_until.isoformat() if task.snoozed_until else None,
        "estimated_minutes": task.estimated_minutes,
        "estimate_source": task.estimate_source,
        "review_skips": _task_review_skips(task),
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def _task_review_skips(task: Task) -> dict[str, bool]:
    skips = (task.metadata_ or {}).get("review_skips")
    if not isinstance(skips, dict):
        return {}
    return {str(key): True for key, value in skips.items() if value is True}


def _merge_review_skips(task: Task, updates: dict[str, Any] | None) -> None:
    if not isinstance(updates, dict):
        return
    metadata = dict(task.metadata_ or {})
    skips = dict(metadata.get("review_skips") or {})
    for key, value in updates.items():
        normalized = str(key)
        if value is True:
            skips[normalized] = True
        elif value is False:
            skips.pop(normalized, None)
    if skips:
        metadata["review_skips"] = skips
    else:
        metadata.pop("review_skips", None)
    task.metadata_ = metadata


def _remember_completed_from_status(task: Task) -> None:
    if task.status == TaskStatus.DONE:
        return
    task.metadata_ = {
        **(task.metadata_ or {}),
        COMPLETED_FROM_STATUS_KEY: task.status.value,
    }


def _reopen_status(task: Task) -> TaskStatus:
    previous = (task.metadata_ or {}).get(COMPLETED_FROM_STATUS_KEY)
    return TaskStatus.INBOX if previous == TaskStatus.INBOX.value else TaskStatus.ACTIVE


def _clear_completed_from_status(task: Task) -> None:
    task.metadata_ = {
        key: value
        for key, value in (task.metadata_ or {}).items()
        if key != COMPLETED_FROM_STATUS_KEY
    }


def _rename_score(wanted: str, title: str) -> float:
    overlap = keyword_overlap(wanted, title)
    ratio = SequenceMatcher(None, wanted, title).ratio()
    score = (overlap * 0.72) + (ratio * 0.28)
    if wanted in title or title in wanted:
        score = max(score, 0.88 + min(overlap, 1.0) * 0.08)
    if overlap >= 0.66:
        score = max(score, 0.74)
    return min(score, 1.0)


def _normalized_tags(tags: list[str] | None) -> set[str]:
    return {
        normalized
        for tag in tags or []
        if (normalized := normalize_for_match(tag.lstrip("#")))
    }


def _dedupe_tags(tags: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags or []:
        text = str(tag).strip().lstrip("#")
        normalized = normalize_for_match(text)
        if text and normalized and normalized not in seen:
            cleaned.append(text[:50])
            seen.add(normalized)
    return cleaned


def _bulk_query_matches(task: Task, wanted: str) -> bool:
    if not wanted:
        return True
    fields = [
        normalize_for_match(task.title),
        normalize_for_match(task.description or ""),
        normalize_for_match(task.project or ""),
        " ".join(sorted(_normalized_tags(task.tags))),
    ]
    for value in fields:
        if not value:
            continue
        if wanted in value or value in wanted:
            return True
        if keyword_overlap(wanted, value) >= 0.5:
            return True
    return False


def _not_snoozed(now: datetime):
    return or_(Task.snoozed_until.is_(None), Task.snoozed_until <= now)


def _next_local_week_start(now: datetime, timezone: str | None) -> datetime:
    zone = get_zone(timezone)
    local_now = now.astimezone(zone) if now.tzinfo else now.replace(tzinfo=zone)
    next_monday = local_now.date() + timedelta(days=7 - local_now.weekday())
    return datetime.combine(next_monday, time.min, tzinfo=zone).astimezone(UTC)


def task_bucket(
    task: Task,
    *,
    timezone: str | None,
    now: datetime | None = None,
) -> TaskBucket | None:
    if task.status == TaskStatus.INBOX:
        return "inbox"
    if task.status == TaskStatus.DONE:
        return "done"
    if task.status != TaskStatus.ACTIVE:
        return None
    if task.target_at is not None and task.target_at < _next_local_week_start(
        now or utc_now(), timezone
    ):
        return "this_week"
    return "later"


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    # --- creation -----------------------------------------------------

    async def create_task(
        self,
        user: User,
        *,
        title: str,
        description: str | None = None,
        priority: str = "medium",
        project: str | None = None,
        project_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        due_at: datetime | None = None,
        target_at: datetime | None = None,
        reminder_at: datetime | None = None,
        estimated_minutes: int | None = None,
        estimate_source: str | None = None,
        source: str = "manual",
        source_message_id: uuid.UUID | None = None,
        created_by: str = "user",
        actor: str = "user",
        agent_run_id: uuid.UUID | None = None,
    ) -> Task:
        due_at = local_to_utc(due_at, user.timezone) if due_at else None
        target_at = local_to_utc(target_at, user.timezone) if target_at else None
        reminder_at = local_to_utc(reminder_at, user.timezone) if reminder_at else None
        project_service = ProjectService(self.session)
        project_row = await project_service.get(user, project_id) if project_id else None
        if project_id is not None and project_row is None:
            raise ValueError("project_not_found")
        if project_row is not None and (project or "").strip():
            if project_row.name.casefold() != str(project).strip().casefold():
                raise ValueError("project_mismatch")
        if project_id is None:
            project_row = await project_service.get_or_create(user, project)
        task = Task(
            user_id=user.id,
            title=title.strip()[:300],
            description=description,
            status=TaskStatus.ACTIVE if target_at is not None else TaskStatus.INBOX,
            priority=Priority(priority),
            project=project_row.name if project_row else project,
            project_id=project_row.id if project_row else None,
            tags=tags or [],
            due_at=due_at,
            target_at=target_at,
            reminder_at=reminder_at,
            estimated_minutes=estimated_minutes,
            estimate_source=estimate_source,
            source=source,
            source_message_id=source_message_id,
            created_by=created_by,
        )
        self.session.add(task)
        await self.session.flush()
        await self._record_event(task, "created", actor=actor, after=_task_snapshot(task),
                                 agent_run_id=agent_run_id)
        await self.audit.log(user_id=user.id, actor=actor, entity_type="task",
                             entity_id=task.id, action="created", details={"title": task.title})
        await self._emit_task_changed(task, "task.created", actor=actor)
        await self._queue_suggestion_refresh(user, task=task, reason="task.created")
        return task

    async def find_active_by_title(self, user: User, title: str) -> Task | None:
        wanted = normalize_for_match(title)
        for task in await self.list_active(user, limit=200):
            if normalize_for_match(task.title) == wanted:
                return task
        return None

    async def find_open_rename_candidates(
        self,
        user: User,
        current_title: str,
        *,
        project: str | None = None,
        tags: list[str] | None = None,
        limit: int = 200,
    ) -> list[Task]:
        wanted = normalize_for_match(current_title)
        if not wanted:
            return []
        tasks = await self._list_open_for_rename(user, limit=limit)
        tasks = self._apply_rename_filters(tasks, project=project, tags=tags)
        return self._rank_title_candidates(tasks, wanted)

    async def find_reopen_task_candidates(
        self,
        user: User,
        current_title: str,
        *,
        limit: int = 200,
    ) -> list[Task]:
        wanted = normalize_for_match(current_title)
        if not wanted:
            return []
        result = await self.session.execute(
            select(Task)
            .where(
                Task.user_id == user.id,
                Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX, TaskStatus.DONE]),
            )
            .order_by(Task.due_at.asc().nulls_last(), Task.priority.desc(), Task.created_at.desc())
            .limit(limit)
        )
        return self._rank_title_candidates(list(result.scalars()), wanted)

    @staticmethod
    def _rank_title_candidates(tasks: list[Task], wanted: str) -> list[Task]:
        exact = [task for task in tasks if normalize_for_match(task.title) == wanted]
        if exact:
            return exact[:RENAME_MAX_CANDIDATES]

        substring = [
            task for task in tasks
            if wanted in normalize_for_match(task.title)
        ]
        if substring:
            return substring[:RENAME_MAX_CANDIDATES]

        scored = [
            candidate for candidate in (
                _ScoredRenameCandidate(
                    task=task,
                    score=_rename_score(wanted, normalize_for_match(task.title)),
                    index=index,
                )
                for index, task in enumerate(tasks)
            )
            if candidate.score >= RENAME_FUZZY_MIN_SCORE
        ]
        if not scored:
            return []
        scored.sort(key=lambda candidate: (-candidate.score, candidate.index))
        top = scored[0]
        close = [
            candidate for candidate in scored
            if top.score - candidate.score <= RENAME_FUZZY_CLEAR_MARGIN
        ]
        if len(close) > 1:
            return [candidate.task for candidate in close[:RENAME_MAX_CANDIDATES]]
        return [top.task]

    async def rename_active_task_by_title(
        self,
        user: User,
        *,
        current_title: str,
        new_title: str,
        project: str | None = None,
        tags: list[str] | None = None,
        actor: str = "user",
        agent_run_id: uuid.UUID | None = None,
    ) -> RenameTaskResult:
        candidates = await self.find_open_rename_candidates(
            user,
            current_title,
            project=project,
            tags=tags,
        )
        if not candidates:
            return RenameTaskResult(status="not_found")
        if len(candidates) > 1:
            return RenameTaskResult(status="ambiguous", candidates=candidates)

        return await self._rename_open_task(
            user,
            candidates[0],
            new_title,
            actor=actor,
            agent_run_id=agent_run_id,
        )

    async def rename_open_task_by_id(
        self,
        user: User,
        task_id: uuid.UUID,
        *,
        new_title: str,
        actor: str = "user",
        agent_run_id: uuid.UUID | None = None,
    ) -> RenameTaskResult:
        task = await self.get(user, task_id)
        if task is None or task.status == TaskStatus.DONE:
            return RenameTaskResult(status="not_found")
        return await self._rename_open_task(
            user,
            task,
            new_title,
            actor=actor,
            agent_run_id=agent_run_id,
        )

    async def _rename_open_task(
        self,
        user: User,
        task: Task,
        new_title: str,
        *,
        actor: str,
        agent_run_id: uuid.UUID | None = None,
    ) -> RenameTaskResult:
        old_title = task.title
        before = _task_snapshot(task)
        task.title = new_title.strip()[:300]
        await self._record_event(
            task,
            "updated",
            actor=actor,
            before=before,
            after=_task_snapshot(task),
            agent_run_id=agent_run_id,
        )
        await self.audit.log(
            user_id=user.id,
            actor=actor,
            entity_type="task",
            entity_id=task.id,
            action="updated",
            details={"old_title": old_title, "new_title": task.title},
        )
        await self._emit_task_changed(task, "task.updated", actor=actor)
        return RenameTaskResult(
            status="renamed",
            task=task,
            old_title=old_title,
            new_title=task.title,
        )

    async def create_task_from_signal(
        self,
        user: User,
        signal: ExtractedTask,
        *,
        source_message_id: uuid.UUID | None = None,
        agent_run_id: uuid.UUID | None = None,
    ) -> Task:
        # The agent must not create the same task twice (repeated phrasing,
        # re-extraction): refresh the existing one instead.
        existing = await self.find_active_by_title(user, signal.title)
        if existing is not None:
            updated = False
            if signal.due_at_local and existing.due_at is None:
                existing.due_at = local_to_utc(signal.due_at_local, user.timezone)
                updated = True
            if signal.reminder_at_local and existing.reminder_at is None:
                existing.reminder_at = local_to_utc(signal.reminder_at_local, user.timezone)
                updated = True
            if updated:
                await self._record_event(existing, "updated", actor="agent",
                                         after=_task_snapshot(existing),
                                         agent_run_id=agent_run_id)
                await self._emit_task_changed(existing, "task.updated", actor="agent")
            return existing

        due_at = local_to_utc(signal.due_at_local, user.timezone) if signal.due_at_local else None
        reminder_at = (
            local_to_utc(signal.reminder_at_local, user.timezone) if signal.reminder_at_local else None
        )
        return await self.create_task(
            user,
            title=signal.title,
            description=signal.description,
            priority=signal.priority,
            project=signal.project,
            tags=signal.tags,
            due_at=due_at,
            reminder_at=reminder_at,
            source="chat",
            source_message_id=source_message_id,
            created_by="agent",
            actor="agent",
            agent_run_id=agent_run_id,
        )

    # --- queries -------------------------------------------------------

    async def get(self, user: User, task_id: uuid.UUID) -> Task | None:
        result = await self.session.execute(
            select(Task).where(Task.id == task_id, Task.user_id == user.id)
        )
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        user: User,
        *,
        filter_: str = "all",
        limit: int = 100,
        project_id: uuid.UUID | None = None,
        q: str | None = None,
        offset: int = 0,
        now: datetime | None = None,
    ) -> list[Task]:
        items, _, _ = await self.list_task_page(
            user,
            filter_=filter_,
            limit=limit,
            project_id=project_id,
            q=q,
            offset=offset,
            now=now,
        )
        return items

    async def list_task_page(
        self,
        user: User,
        *,
        filter_: str = "all",
        limit: int = 100,
        project_id: uuid.UUID | None = None,
        q: str | None = None,
        offset: int = 0,
        now: datetime | None = None,
    ) -> tuple[list[Task], bool, int | None]:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        stmt = select(Task).where(Task.user_id == user.id)
        if project_id is not None:
            stmt = stmt.where(Task.project_id == project_id)
        now = now or utc_now()
        _, day_end = local_day_bounds(now, user.timezone)
        next_week_start = _next_local_week_start(now, user.timezone)
        active = Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX])
        visible_active = active & _not_snoozed(now)

        if filter_ == "inbox":
            stmt = stmt.where(Task.status == TaskStatus.INBOX, _not_snoozed(now))
            stmt = stmt.order_by(Task.created_at.desc(), Task.id.desc())
        elif filter_ == "this_week":
            stmt = stmt.where(
                Task.status == TaskStatus.ACTIVE,
                _not_snoozed(now),
                Task.target_at.is_not(None),
                Task.target_at < next_week_start,
            )
            stmt = stmt.order_by(
                Task.target_at.asc(),
                Task.due_at.asc().nulls_last(),
                Task.created_at.desc(),
                Task.id.desc(),
            )
        elif filter_ == "later":
            stmt = stmt.where(
                Task.status == TaskStatus.ACTIVE,
                _not_snoozed(now),
                or_(Task.target_at.is_(None), Task.target_at >= next_week_start),
            )
            stmt = stmt.order_by(
                Task.target_at.asc().nulls_last(),
                Task.due_at.asc().nulls_last(),
                Task.created_at.desc(),
                Task.id.desc(),
            )
        elif filter_ == "done":
            stmt = stmt.where(Task.status == TaskStatus.DONE)
            stmt = stmt.order_by(Task.completed_at.desc(), Task.id.desc())
        elif filter_ == "today":
            stmt = stmt.where(visible_active, Task.due_at.is_not(None), Task.due_at < day_end)
            stmt = stmt.order_by(Task.due_at.asc(), Task.id.desc())
        elif filter_ == "upcoming":
            stmt = stmt.where(visible_active, or_(Task.due_at.is_(None), Task.due_at >= day_end))
            stmt = stmt.order_by(
                Task.due_at.asc().nulls_last(), Task.created_at.desc(), Task.id.desc()
            )
        elif filter_ == "review":
            stmt = stmt.where(Task.status == TaskStatus.INBOX, _not_snoozed(now))
            stmt = stmt.order_by(Task.created_at.desc(), Task.id.desc())
        else:
            stmt = stmt.where(visible_active).order_by(
                Task.due_at.asc().nulls_last(), Task.created_at.desc(), Task.id.desc()
            )

        search = " ".join((q or "").split()).strip()
        if search:
            stmt = stmt.where(or_(
                Task.title.icontains(search, autoescape=True),
                Task.description.icontains(search, autoescape=True),
                Task.project.icontains(search, autoescape=True),
                func.array_to_string(Task.tags, " ").icontains(search, autoescape=True),
            ))

        result = await self.session.execute(stmt.offset(offset).limit(limit + 1))
        items = list(result.scalars())
        has_more = len(items) > limit
        page = items[:limit]
        return page, has_more, offset + len(page) if has_more else None

    async def list_active(self, user: User, limit: int = 50) -> list[Task]:
        now = utc_now()
        result = await self.session.execute(
            select(Task)
            .where(
                Task.user_id == user.id,
                Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX]),
                _not_snoozed(now),
            )
            .execution_options(populate_existing=True)
            .order_by(Task.due_at.asc().nulls_last(), Task.priority.desc(), Task.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def find_bulk_update_candidates(
        self,
        user: User,
        *,
        task_query: str | None = None,
        from_project: str | None = None,
        from_tags: list[str] | None = None,
        status: Literal["open", "all"] = "open",
        limit: int = 50,
    ) -> list[Task]:
        fetch_limit = max(200, min(max(limit, 1) * 5, 1000))
        stmt = select(Task).where(Task.user_id == user.id)
        if status == "open":
            stmt = stmt.where(Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX]))
        stmt = stmt.order_by(
            Task.due_at.asc().nulls_last(),
            Task.priority.desc(),
            Task.created_at.desc(),
        )
        result = await self.session.execute(stmt.limit(fetch_limit))
        tasks = list(result.scalars())

        wanted_project = normalize_for_match(from_project or "")
        if wanted_project:
            tasks = [
                task for task in tasks
                if normalize_for_match(task.project or "") == wanted_project
            ]

        wanted_tags = _normalized_tags(from_tags)
        if wanted_tags:
            tasks = [
                task for task in tasks
                if wanted_tags.issubset(_normalized_tags(task.tags))
            ]

        wanted_query = normalize_for_match(task_query or "")
        if wanted_query:
            tasks = [task for task in tasks if _bulk_query_matches(task, wanted_query)]

        return tasks[:max(1, min(limit, 100))]

    async def _list_open_for_rename(self, user: User, limit: int = 200) -> list[Task]:
        result = await self.session.execute(
            select(Task)
            .where(Task.user_id == user.id, Task.status != TaskStatus.DONE)
            .order_by(Task.due_at.asc().nulls_last(), Task.priority.desc(), Task.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    @staticmethod
    def _apply_rename_filters(
        tasks: list[Task],
        *,
        project: str | None,
        tags: list[str] | None,
    ) -> list[Task]:
        filtered = tasks
        if project:
            wanted_project = normalize_for_match(project)
            filtered = [
                task for task in filtered
                if normalize_for_match(task.project or "") == wanted_project
            ]
        wanted_tags = _normalized_tags(tags)
        if wanted_tags:
            filtered = [
                task for task in filtered
                if wanted_tags.issubset(_normalized_tags(task.tags))
            ]
        return filtered

    async def count_summary(self, user: User) -> dict[str, int]:
        now = utc_now()
        _, day_end = local_day_bounds(now, user.timezone)
        tasks = await self.list_active(user, limit=500)
        due_today = [t for t in tasks if t.due_at and t.due_at < day_end and t.due_at >= now]
        overdue = [t for t in tasks if t.due_at and t.due_at < now]
        return {
            "tasks_active": len(tasks),
            "tasks_due_today": len(due_today),
            "tasks_overdue": len(overdue),
        }

    # --- mutations -----------------------------------------------------

    async def update_task(
        self,
        user: User,
        task: Task,
        updates: dict[str, Any],
        *,
        actor: str = "user",
        agent_run_id: uuid.UUID | None = None,
    ) -> Task:
        before = _task_snapshot(task)
        normalized = dict(updates)
        for key in ("due_at", "target_at", "reminder_at"):
            value = normalized.get(key)
            if isinstance(value, datetime):
                normalized[key] = local_to_utc(value, user.timezone)

        requested_status = None
        if normalized.get("status") is not None:
            requested_status = TaskStatus(normalized["status"])
        target_supplied = "target_at" in normalized
        target_at = normalized.get("target_at")
        if requested_status == TaskStatus.INBOX and target_at is not None:
            raise ValueError("inbox_cannot_have_planned_for")

        project_by_id: Project | None = None
        project_name = normalized.get("project")
        raw_project_id = normalized.get("project_id")
        if (
            "project_id" in normalized
            and raw_project_id is None
            and isinstance(project_name, str)
            and project_name.strip()
        ):
            # A supplied project name is authoritative, matching create semantics.
            normalized.pop("project_id")
        if raw_project_id is not None:
            try:
                project_id = (
                    raw_project_id
                    if isinstance(raw_project_id, uuid.UUID)
                    else uuid.UUID(str(raw_project_id))
                )
            except (TypeError, ValueError, AttributeError):
                raise ValueError("project_not_found") from None
            normalized["project_id"] = project_id
            project_by_id = await ProjectService(self.session).get(user, project_id)
            if project_by_id is None:
                raise ValueError("project_not_found")
            if (
                isinstance(project_name, str)
                and project_name.strip()
                and project_name.strip().casefold() != project_by_id.name.casefold()
            ):
                raise ValueError("project_mismatch")

        allowed = {"title", "description", "priority", "project", "project_id", "tags",
                   "due_at", "target_at", "reminder_at", "status", "estimated_minutes",
                   "estimate_source", "review_skips"}
        for key, value in normalized.items():
            if key not in allowed or value is None and key in ("title",):
                continue
            if key in {"status", "target_at"}:
                continue
            if key == "review_skips":
                _merge_review_skips(task, value)
                continue
            if key == "priority" and value is not None:
                value = Priority(value)
            if key == "project":
                project_row = project_by_id or await ProjectService(self.session).get_or_create(
                    user, value
                )
                task.project_id = project_row.id if project_row else None
                value = project_row.name if project_row else value
            if key == "project_id":
                project_row = project_by_id if value is not None else None
                if value is not None and project_row is None:
                    raise ValueError("project_not_found")
                task.project = project_row.name if project_row else None
                value = project_row.id if project_row else None
            setattr(task, key, value)

        if requested_status == TaskStatus.DONE:
            if task.status != TaskStatus.DONE:
                _remember_completed_from_status(task)
                task.completed_at = utc_now()
            task.status = TaskStatus.DONE
        elif requested_status is not None:
            if task.status == TaskStatus.DONE and requested_status == TaskStatus.ACTIVE:
                requested_status = _reopen_status(task)
            task.status = requested_status
            task.completed_at = None
            _clear_completed_from_status(task)

        if target_supplied:
            task.target_at = target_at
            if target_at is not None and task.status == TaskStatus.INBOX:
                task.status = TaskStatus.ACTIVE
        if task.status == TaskStatus.INBOX:
            task.target_at = None

        after = _task_snapshot(task)
        if after == before:
            return task
        await self._record_event(
            task,
            "updated",
            actor=actor,
            before=before,
            after=after,
            agent_run_id=agent_run_id,
        )
        await self._emit_task_changed(task, "task.updated", actor=actor)
        await self._queue_suggestion_refresh(user, task=task, reason="task.updated")
        return task

    async def update_task_with_tag_ops(
        self,
        user: User,
        task: Task,
        updates: dict[str, Any],
        *,
        tags_add: list[str] | None = None,
        tags_remove: list[str] | None = None,
        actor: str = "user",
        agent_run_id: uuid.UUID | None = None,
    ) -> Task:
        effective_updates = dict(updates)
        if tags_add or tags_remove:
            current_tags = _dedupe_tags(
                effective_updates["tags"] if "tags" in effective_updates else task.tags
            )
            remove = _normalized_tags(tags_remove)
            if remove:
                current_tags = [
                    tag for tag in current_tags
                    if normalize_for_match(tag) not in remove
                ]
            existing = _normalized_tags(current_tags)
            for tag in _dedupe_tags(tags_add):
                normalized = normalize_for_match(tag)
                if normalized and normalized not in existing:
                    current_tags.append(tag)
                    existing.add(normalized)
            effective_updates["tags"] = current_tags
        return await self.update_task(
            user,
            task,
            effective_updates,
            actor=actor,
            agent_run_id=agent_run_id,
        )

    async def bulk_update_tasks(
        self,
        user: User,
        tasks: list[Task],
        updates: dict[str, Any],
        *,
        tags_add: list[str] | None = None,
        tags_remove: list[str] | None = None,
        actor: str = "user",
        agent_run_id: uuid.UUID | None = None,
    ) -> list[Task]:
        updated: list[Task] = []
        for task in tasks:
            updated.append(await self.update_task_with_tag_ops(
                user,
                task,
                updates,
                tags_add=tags_add,
                tags_remove=tags_remove,
                actor=actor,
                agent_run_id=agent_run_id,
            ))
        return updated

    async def complete_task(self, user: User, task: Task, *, actor: str = "user") -> Task:
        if task.status == TaskStatus.DONE:
            return task
        before = _task_snapshot(task)
        _remember_completed_from_status(task)
        task.status = TaskStatus.DONE
        task.completed_at = utc_now()
        await self._record_event(task, "completed", actor=actor, before=before,
                                 after=_task_snapshot(task))
        await self.audit.log(user_id=user.id, actor=actor, entity_type="task",
                             entity_id=task.id, action="completed", details={"title": task.title})
        await self._emit_task_changed(task, "task.completed", actor=actor)
        await self._queue_suggestion_refresh(user, task=task, reason="task.completed")
        return task

    async def snooze_task(
        self, user: User, task: Task, *, preset: str | None = None,
        until: datetime | None = None, actor: str = "user",
    ) -> Task:
        before = _task_snapshot(task)
        if until is None:
            if preset in SNOOZE_PRESETS:
                until = utc_now() + SNOOZE_PRESETS[preset]
            elif preset == "tomorrow":
                day_start, _ = local_day_bounds(utc_now() + timedelta(days=1), user.timezone)
                until = day_start + timedelta(hours=9)
            elif preset == "next_week":
                day_start, _ = local_day_bounds(utc_now() + timedelta(days=7), user.timezone)
                until = day_start + timedelta(hours=9)
            else:
                until = utc_now() + timedelta(hours=1)
        else:
            until = local_to_utc(until, user.timezone)
        task.snoozed_until = until
        task.reminder_at = until
        task.metadata_ = {k: v for k, v in task.metadata_.items() if k != "reminder_sent_at"}
        await self._record_event(task, "snoozed", actor=actor, before=before,
                                 after=_task_snapshot(task))
        await self._emit_task_changed(task, "task.snoozed", actor=actor)
        return task

    # --- reminders -----------------------------------------------------

    async def find_due_reminders(self, now: datetime | None = None) -> list[Task]:
        """Across all users: active tasks whose reminder time has come and was not sent yet."""
        now = now or utc_now()
        result = await self.session.execute(
            select(Task).where(
                Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX]),
                Task.reminder_at.is_not(None),
                Task.reminder_at <= now,
                or_(Task.snoozed_until.is_(None), Task.snoozed_until <= now),
                Task.metadata_["reminder_sent_at"].astext.is_(None),
            )
        )
        return list(result.scalars())

    async def mark_reminder_sent(self, task: Task) -> None:
        task.metadata_ = {**task.metadata_, "reminder_sent_at": utc_now().isoformat()}
        await self._emit_task_changed(task, "task.reminder_sent", actor="system")

    # ------------------------------------------------------------------

    async def _record_event(
        self,
        task: Task,
        event_type: str,
        *,
        actor: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        agent_run_id: uuid.UUID | None = None,
    ) -> None:
        self.session.add(
            TaskEvent(
                task_id=task.id,
                user_id=task.user_id,
                event_type=event_type,
                before_json=before,
                after_json=after,
                actor=actor,
                agent_run_id=agent_run_id,
            )
        )

    async def _emit_task_changed(self, task: Task, event_type: str, *, actor: str) -> None:
        await RealtimeEventService(self.session).emit(
            user_id=task.user_id,
            topics=["tasks", "projects"],
            event_type=event_type,
            payload={"task_id": str(task.id), "actor": actor},
        )

    async def _queue_suggestion_refresh(self, user: User, *, task: Task, reason: str) -> None:
        if task.status != TaskStatus.INBOX:
            return
        await AssistantSuggestionService(self.session).enqueue_opportunity(
            user,
            kind="task_cleanup",
            scope_key="review",
            reason=reason,
            payload={"task_id": str(task.id), "project_id": str(task.project_id) if task.project_id else None},
            delay_seconds=45,
        )
