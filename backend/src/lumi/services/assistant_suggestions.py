"""Persistent proactive assistant suggestions for Tasks/Projects UI."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import (
    AssistantOpportunityJob,
    AssistantSuggestion,
    AssistantSuggestionStatus,
    User,
)
from lumi.services.realtime import RealtimeEventService
from lumi.utils.time import utc_now


class AssistantSuggestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user: User,
        *,
        kind: str,
        title: str,
        description: str | None = None,
        payload: dict[str, Any] | None = None,
        context_hash: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        affected_task_ids: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> AssistantSuggestion:
        if context_hash:
            existing = await self._pending_by_context(user, kind=kind, context_hash=context_hash)
            if existing is not None:
                existing.title = title.strip()[:300]
                existing.description = description
                existing.payload = dict(payload or {})
                existing.start_at = start_at
                existing.end_at = end_at
                existing.affected_task_ids = affected_task_ids or []
                existing.expires_at = expires_at
                await self._emit(user, "assistant_suggestion.updated", existing)
                return existing

        suggestion = AssistantSuggestion(
            user_id=user.id,
            kind=kind,
            title=title.strip()[:300],
            description=description,
            payload=dict(payload or {}),
            context_hash=context_hash,
            start_at=start_at,
            end_at=end_at,
            affected_task_ids=affected_task_ids or [],
            expires_at=expires_at,
        )
        self.session.add(suggestion)
        await self.session.flush()
        await self._emit(user, "assistant_suggestion.created", suggestion)
        return suggestion

    async def list_pending(self, user: User, *, kind: str | None = None, limit: int = 20) -> list[AssistantSuggestion]:
        now = utc_now()
        stmt = select(AssistantSuggestion).where(
            AssistantSuggestion.user_id == user.id,
            AssistantSuggestion.status == AssistantSuggestionStatus.PENDING,
        )
        if kind:
            stmt = stmt.where(AssistantSuggestion.kind == kind)
        stmt = stmt.where(
            (AssistantSuggestion.expires_at.is_(None)) | (AssistantSuggestion.expires_at > now)
        )
        result = await self.session.execute(
            stmt.order_by(
                AssistantSuggestion.start_at.asc().nulls_last(),
                AssistantSuggestion.created_at.desc(),
            ).limit(limit)
        )
        return list(result.scalars())

    async def get(self, user: User, suggestion_id: uuid.UUID) -> AssistantSuggestion | None:
        result = await self.session.execute(
            select(AssistantSuggestion).where(
                AssistantSuggestion.id == suggestion_id,
                AssistantSuggestion.user_id == user.id,
            )
        )
        return result.scalar_one_or_none()

    async def dismiss(self, user: User, suggestion: AssistantSuggestion) -> AssistantSuggestion:
        suggestion.status = AssistantSuggestionStatus.DISMISSED
        suggestion.decided_at = utc_now()
        await self._emit(user, "assistant_suggestion.dismissed", suggestion)
        return suggestion

    async def accept(self, user: User, suggestion: AssistantSuggestion) -> AssistantSuggestion:
        await self._apply_accept_side_effect(user, suggestion)
        suggestion.status = AssistantSuggestionStatus.ACCEPTED
        suggestion.decided_at = utc_now()
        await self._emit(user, "assistant_suggestion.accepted", suggestion)
        return suggestion

    async def _apply_accept_side_effect(self, user: User, suggestion: AssistantSuggestion) -> None:
        if suggestion.kind not in {"task_estimate", "task_due_date", "task_project"}:
            return
        task_id_raw = suggestion.payload.get("task_id")
        if not isinstance(task_id_raw, str):
            return
        try:
            task_id = uuid.UUID(task_id_raw)
        except ValueError:
            return
        from lumi.services.tasks import TaskService

        tasks = TaskService(self.session)
        task = await tasks.get(user, task_id)
        if task is None:
            return
        if suggestion.kind == "task_estimate":
            minutes_raw = suggestion.payload.get("estimated_minutes")
            if not isinstance(minutes_raw, int) or minutes_raw < 1 or minutes_raw > 1440:
                return
            await tasks.update_task(
                user,
                task,
                {"estimated_minutes": minutes_raw, "estimate_source": "assistant"},
                actor="agent",
            )
            return
        if suggestion.kind == "task_due_date":
            due_at_raw = suggestion.payload.get("due_at")
            if suggestion.payload.get("no_deadline") is True or due_at_raw is None:
                await tasks.update_task(
                    user,
                    task,
                    {"review_skips": {"due_date": True}},
                    actor="agent",
                )
                return
            if not isinstance(due_at_raw, str):
                return
            try:
                due_at = datetime.fromisoformat(due_at_raw.replace("Z", "+00:00"))
            except ValueError:
                return
            await tasks.update_task(
                user,
                task,
                {"due_at": due_at, "review_skips": {"due_date": False}},
                actor="agent",
            )
            return
        if suggestion.kind == "task_project":
            project_updates: dict[str, Any] = {"review_skips": {"project": False}}
            project_id_raw = suggestion.payload.get("project_id")
            project_name_raw = suggestion.payload.get("project")
            if isinstance(project_id_raw, str):
                try:
                    project_updates["project_id"] = uuid.UUID(project_id_raw)
                except ValueError:
                    return
            elif isinstance(project_name_raw, str) and project_name_raw.strip():
                project_updates["project"] = project_name_raw
            else:
                return
            await tasks.update_task(user, task, project_updates, actor="agent")
            return

    async def enqueue_opportunity(
        self,
        user: User,
        *,
        kind: str,
        scope_key: str = "default",
        reason: str = "event",
        payload: dict[str, Any] | None = None,
        delay_seconds: int = 30,
    ) -> AssistantOpportunityJob:
        now = utc_now()
        due = now + timedelta(seconds=max(0, delay_seconds))
        result = await self.session.execute(
            select(AssistantOpportunityJob).where(
                AssistantOpportunityJob.user_id == user.id,
                AssistantOpportunityJob.kind == kind,
                AssistantOpportunityJob.scope_key == scope_key,
            )
        )
        job = result.scalar_one_or_none()
        if job is None:
            job = AssistantOpportunityJob(
                user_id=user.id,
                kind=kind,
                scope_key=scope_key,
                reason=reason,
                payload=dict(payload or {}),
                next_check_at=due,
                debounce_until=due,
            )
            self.session.add(job)
        else:
            job.reason = reason
            job.payload = {**(job.payload or {}), **dict(payload or {})}
            job.next_check_at = min(job.next_check_at, due) if job.next_check_at else due
            job.debounce_until = due
        await self.session.flush()
        await RealtimeEventService(self.session).emit(
            user_id=user.id,
            topics=["suggestions"],
            event_type="assistant_opportunity.queued",
            payload={"job_id": str(job.id), "kind": job.kind},
        )
        return job

    async def _pending_by_context(
        self,
        user: User,
        *,
        kind: str,
        context_hash: str,
    ) -> AssistantSuggestion | None:
        result = await self.session.execute(
            select(AssistantSuggestion).where(
                AssistantSuggestion.user_id == user.id,
                AssistantSuggestion.kind == kind,
                AssistantSuggestion.context_hash == context_hash,
                AssistantSuggestion.status == AssistantSuggestionStatus.PENDING,
            )
        )
        return result.scalar_one_or_none()

    async def _emit(self, user: User, event_type: str, suggestion: AssistantSuggestion) -> None:
        await RealtimeEventService(self.session).emit(
            user_id=user.id,
            topics=["suggestions", "today"],
            event_type=event_type,
            payload={"suggestion_id": str(suggestion.id), "kind": suggestion.kind},
        )
