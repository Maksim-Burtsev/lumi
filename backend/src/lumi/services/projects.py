"""ProjectService: first-class project rows backed by legacy task.project compatibility."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import Priority, Project, ProjectStatus, Task, TaskStatus, User
from lumi.services.realtime import RealtimeEventService
from lumi.utils.text import normalize_for_match
from lumi.utils.time import utc_now


def normalize_project_name(name: str) -> str:
    return normalize_for_match(name)


BACKLOG_PROJECT_NAME = "Backlog"
BACKLOG_SYSTEM_KEY = "backlog"


def project_system_key(project: Project) -> str | None:
    value = (project.metadata_ or {}).get("system_key")
    return value if isinstance(value, str) and value else None


def is_system_project(project: Project) -> bool:
    return project_system_key(project) is not None


@dataclass(slots=True)
class ProjectSummary:
    project: Project
    active_task_count: int
    completed_task_count: int
    estimated_minutes_total: int
    next_task: Task | None
    health_status: str
    health_reason: str


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, user: User, name: str | None) -> Project | None:
        clean = (name or "").strip()
        if not clean:
            return None
        normalized = normalize_project_name(clean)
        if normalized == BACKLOG_SYSTEM_KEY:
            return await self.ensure_backlog_project(user)
        result = await self.session.execute(
            select(Project).where(Project.user_id == user.id, Project.normalized_name == normalized)
        )
        project = result.scalar_one_or_none()
        if project is not None:
            if project.name != clean:
                project.name = clean[:200]
            return project
        project = Project(
            user_id=user.id,
            name=clean[:200],
            normalized_name=normalized,
            status=ProjectStatus.ACTIVE,
        )
        self.session.add(project)
        await self.session.flush()
        await RealtimeEventService(self.session).emit(
            user_id=user.id,
            topics=["projects"],
            event_type="project.created",
            payload={"project_id": str(project.id)},
        )
        return project

    async def ensure_backlog_project(self, user: User) -> Project:
        result = await self.session.execute(
            select(Project).where(
                Project.user_id == user.id,
                Project.normalized_name == BACKLOG_SYSTEM_KEY,
            )
        )
        project = result.scalar_one_or_none()
        metadata = {"system_key": BACKLOG_SYSTEM_KEY, "is_system": True}
        if project is not None:
            changed = False
            if project.name != BACKLOG_PROJECT_NAME:
                project.name = BACKLOG_PROJECT_NAME
                changed = True
            if project.status != ProjectStatus.ACTIVE:
                project.status = ProjectStatus.ACTIVE
                changed = True
            merged = {**(project.metadata_ or {}), **metadata}
            if merged != (project.metadata_ or {}):
                project.metadata_ = merged
                changed = True
            if changed:
                await self.session.flush()
            return project

        project = Project(
            user_id=user.id,
            name=BACKLOG_PROJECT_NAME,
            normalized_name=BACKLOG_SYSTEM_KEY,
            status=ProjectStatus.ACTIVE,
            metadata_=metadata,
        )
        self.session.add(project)
        await self.session.flush()
        await RealtimeEventService(self.session).emit(
            user_id=user.id,
            topics=["projects"],
            event_type="project.created",
            payload={"project_id": str(project.id), "system_key": BACKLOG_SYSTEM_KEY},
        )
        return project

    async def get(self, user: User, project_id: uuid.UUID) -> Project | None:
        result = await self.session.execute(
            select(Project).where(Project.id == project_id, Project.user_id == user.id)
        )
        return result.scalar_one_or_none()

    async def list_summaries(self, user: User) -> list[ProjectSummary]:
        await self.ensure_backlog_project(user)
        await self._backfill_missing_projects(user)
        await self._backfill_backlog_tasks(user)
        counts = await self._counts(user)
        next_tasks = await self._next_tasks(user)
        last_updates = await self._last_updates(user)

        result = await self.session.execute(
            select(Project)
            .where(Project.user_id == user.id, Project.status == ProjectStatus.ACTIVE)
            .order_by(Project.name.asc())
        )
        summaries: list[ProjectSummary] = []
        for project in result.scalars():
            key = project.id
            count = counts.get(key, {})
            next_task = next_tasks.get(key)
            summaries.append(
                ProjectSummary(
                    project=project,
                    active_task_count=int(count.get("active", 0)),
                    completed_task_count=int(count.get("done", 0)),
                    estimated_minutes_total=int(count.get("estimate", 0)),
                    next_task=next_task,
                    **_project_health(
                        project=project,
                        active_task_count=int(count.get("active", 0)),
                        next_task=next_task,
                        last_task_update=last_updates.get(key),
                    ),
                )
            )
        rank = {"needs_attention": 0, "moving": 1, "light": 2, "quiet": 3}
        summaries.sort(key=lambda item: (
            rank.get(item.health_status, 9),
            item.next_task is None,
            -item.active_task_count,
            item.project.name.lower(),
        ))
        return summaries

    async def _backfill_missing_projects(self, user: User) -> None:
        result = await self.session.execute(
            select(Task.project)
            .where(Task.user_id == user.id, Task.project.is_not(None), Task.project != "", Task.project_id.is_(None))
            .distinct()
        )
        for name in result.scalars():
            project = await self.get_or_create(user, name)
            if project is None:
                continue
            await self.session.execute(
                Task.__table__.update()
                .where(
                    Task.user_id == user.id,
                    Task.project_id.is_(None),
                    func.lower(func.btrim(Task.project)) == project.normalized_name,
                )
                .values(project_id=project.id)
            )
        await self.session.flush()

    async def _backfill_backlog_tasks(self, user: User) -> None:
        backlog = await self.ensure_backlog_project(user)
        await self.session.execute(
            Task.__table__.update()
            .where(
                Task.user_id == user.id,
                Task.project_id.is_(None),
                or_(Task.project.is_(None), func.btrim(Task.project) == ""),
                Task.due_at.is_(None),
                Task.target_at.is_(None),
                Task.reminder_at.is_(None),
                Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX]),
            )
            .values(project_id=backlog.id, project=backlog.name)
        )
        await self.session.flush()

    async def _counts(self, user: User) -> dict[uuid.UUID, dict[str, Any]]:
        result = await self.session.execute(
            select(
                Task.project_id,
                Task.status,
                func.count(Task.id),
                func.coalesce(func.sum(Task.estimated_minutes), 0),
            )
            .where(Task.user_id == user.id, Task.project_id.is_not(None))
            .group_by(Task.project_id, Task.status)
        )
        counts: dict[uuid.UUID, dict[str, Any]] = {}
        for project_id, status, count, estimate in result.all():
            bucket = counts.setdefault(project_id, {"active": 0, "done": 0, "estimate": 0})
            if status in (TaskStatus.ACTIVE, TaskStatus.INBOX):
                bucket["active"] += int(count)
                bucket["estimate"] += int(estimate or 0)
            elif status == TaskStatus.DONE:
                bucket["done"] += int(count)
        return counts

    async def _next_tasks(self, user: User) -> dict[uuid.UUID, Task]:
        result = await self.session.execute(
            select(Task)
            .where(
                Task.user_id == user.id,
                Task.project_id.is_not(None),
                Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX]),
            )
            .order_by(
                Task.due_at.asc().nulls_last(),
                Task.priority.desc(),
                Task.created_at.desc(),
            )
            .limit(500)
        )
        next_by_project: dict[uuid.UUID, Task] = {}
        priority_rank = {
            Priority.URGENT: 4,
            Priority.HIGH: 3,
            Priority.MEDIUM: 2,
            Priority.LOW: 1,
        }
        for task in result.scalars():
            current = next_by_project.get(task.project_id)
            if current is None or priority_rank[task.priority] > priority_rank[current.priority]:
                next_by_project[task.project_id] = task
        return next_by_project

    async def _last_updates(self, user: User) -> dict[uuid.UUID, datetime]:
        result = await self.session.execute(
            select(Task.project_id, func.max(Task.updated_at))
            .where(Task.user_id == user.id, Task.project_id.is_not(None))
            .group_by(Task.project_id)
        )
        return {project_id: updated_at for project_id, updated_at in result.all() if updated_at}


def _project_health(
    *,
    project: Project,
    active_task_count: int,
    next_task: Task | None,
    last_task_update: datetime | None,
) -> dict[str, str]:
    now = utc_now()
    last_update = max(project.updated_at, last_task_update or project.updated_at)
    quiet_days = max(0, (now - last_update).days)
    if next_task and next_task.due_at and next_task.due_at < now:
        return {"health_status": "needs_attention", "health_reason": "Overdue task"}
    if active_task_count > 0 and quiet_days >= 4:
        return {"health_status": "needs_attention", "health_reason": f"Quiet {quiet_days} days"}
    if active_task_count == 0:
        return {"health_status": "light", "health_reason": "No open tasks"}
    if next_task and next_task.estimated_minutes and next_task.estimated_minutes <= 10:
        return {"health_status": "light", "health_reason": f"{next_task.estimated_minutes} min task"}
    if quiet_days == 0:
        return {"health_status": "moving", "health_reason": "Updated today"}
    if next_task is not None:
        return {"health_status": "moving", "health_reason": "Next move ready"}
    return {"health_status": "quiet", "health_reason": f"Quiet {quiet_days} days"}
