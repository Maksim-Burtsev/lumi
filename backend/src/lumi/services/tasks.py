"""TaskService: create/complete/snooze tasks, reminders, audit trail."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.schemas import ExtractedTask
from lumi.db.models import Priority, Task, TaskEvent, TaskStatus, User
from lumi.services.audit import AuditService
from lumi.services.realtime import RealtimeEventService
from lumi.utils.text import keyword_overlap, normalize_for_match
from lumi.utils.time import local_day_bounds, local_to_utc, utc_now

SNOOZE_PRESETS = {"1h": timedelta(hours=1), "3h": timedelta(hours=3)}
RENAME_FUZZY_MIN_SCORE = 0.58
RENAME_FUZZY_CLEAR_MARGIN = 0.16
RENAME_MAX_CANDIDATES = 5


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
        "status": task.status.value if isinstance(task.status, TaskStatus) else task.status,
        "priority": task.priority.value if isinstance(task.priority, Priority) else task.priority,
        "project": task.project,
        "tags": task.tags or [],
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "reminder_at": task.reminder_at.isoformat() if task.reminder_at else None,
        "snoozed_until": task.snoozed_until.isoformat() if task.snoozed_until else None,
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
        tags: list[str] | None = None,
        due_at: datetime | None = None,
        reminder_at: datetime | None = None,
        source: str = "manual",
        source_message_id: uuid.UUID | None = None,
        created_by: str = "user",
        actor: str = "user",
        agent_run_id: uuid.UUID | None = None,
    ) -> Task:
        task = Task(
            user_id=user.id,
            title=title.strip()[:300],
            description=description,
            status=TaskStatus.ACTIVE,
            priority=Priority(priority),
            project=project,
            tags=tags or [],
            due_at=due_at,
            reminder_at=reminder_at,
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

    async def list_tasks(self, user: User, *, filter_: str = "all", limit: int = 100) -> list[Task]:
        stmt = select(Task).where(Task.user_id == user.id)
        now = utc_now()
        day_start, day_end = local_day_bounds(now, user.timezone)
        active = Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX])
        visible_active = active & _not_snoozed(now)

        if filter_ == "today":
            stmt = stmt.where(visible_active, Task.due_at.is_not(None), Task.due_at < day_end)
            stmt = stmt.order_by(Task.due_at.asc())
        elif filter_ == "upcoming":
            stmt = stmt.where(visible_active, or_(Task.due_at.is_(None), Task.due_at >= day_end))
            stmt = stmt.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc())
        elif filter_ == "inbox":
            stmt = stmt.where(
                Task.status == TaskStatus.INBOX,
                _not_snoozed(now),
            ).order_by(Task.created_at.desc())
        elif filter_ == "done":
            stmt = stmt.where(Task.status == TaskStatus.DONE).order_by(Task.completed_at.desc())
        else:
            stmt = stmt.where(visible_active).order_by(
                Task.due_at.asc().nulls_last(), Task.created_at.desc()
            )
        result = await self.session.execute(stmt.limit(limit))
        return list(result.scalars())

    async def list_active(self, user: User, limit: int = 50) -> list[Task]:
        now = utc_now()
        result = await self.session.execute(
            select(Task)
            .where(
                Task.user_id == user.id,
                Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX]),
                _not_snoozed(now),
            )
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
        allowed = {"title", "description", "priority", "project", "tags",
                   "due_at", "reminder_at", "status"}
        for key, value in updates.items():
            if key not in allowed or value is None and key in ("title",):
                continue
            if key == "priority" and value is not None:
                value = Priority(value)
            if key == "status" and value is not None:
                value = TaskStatus(value)
                if value == TaskStatus.DONE and task.completed_at is None:
                    task.completed_at = utc_now()
                elif value != TaskStatus.DONE:
                    task.completed_at = None
            setattr(task, key, value)
        await self._record_event(
            task,
            "updated",
            actor=actor,
            before=before,
            after=_task_snapshot(task),
            agent_run_id=agent_run_id,
        )
        await self._emit_task_changed(task, "task.updated", actor=actor)
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
        before = _task_snapshot(task)
        task.status = TaskStatus.DONE
        task.completed_at = utc_now()
        await self._record_event(task, "completed", actor=actor, before=before,
                                 after=_task_snapshot(task))
        await self.audit.log(user_id=user.id, actor=actor, entity_type="task",
                             entity_id=task.id, action="completed", details={"title": task.title})
        await self._emit_task_changed(task, "task.completed", actor=actor)
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
            topics=["tasks"],
            event_type=event_type,
            payload={"task_id": str(task.id), "actor": actor},
        )
