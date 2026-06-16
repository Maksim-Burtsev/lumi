"""Agent run lifecycle + tool call logging."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import AgentRun, AgentRunType, RunStatus, ToolCall
from lumi.services.realtime import RealtimeEventService
from lumi.utils.text import truncate
from lumi.utils.time import utc_now


class RunService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        type_: AgentRunType,
        trigger: str,
        scheduled_task_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        source_message_id: uuid.UUID | None = None,
        input_summary: str | None = None,
    ) -> AgentRun:
        run = AgentRun(
            user_id=user_id,
            type=type_,
            status=RunStatus.QUEUED,
            trigger=trigger,
            scheduled_task_id=scheduled_task_id,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            input_summary=truncate(input_summary, 1000) if input_summary else None,
        )
        self.session.add(run)
        await self.session.flush()
        await self._emit_run_changed(run, "run.created")
        return run

    async def get(self, run_id: uuid.UUID, user_id: uuid.UUID) -> AgentRun | None:
        result = await self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def mark_running(self, run: AgentRun) -> None:
        run.status = RunStatus.RUNNING
        run.started_at = utc_now()
        await self._emit_run_changed(run, "run.running")

    async def mark_completed(self, run: AgentRun, result_summary: str | None = None) -> None:
        run.status = RunStatus.COMPLETED
        run.finished_at = utc_now()
        if result_summary:
            run.result_summary = truncate(result_summary, 2000)
        await self._emit_run_changed(run, "run.completed")

    async def mark_failed(self, run: AgentRun, error: str) -> None:
        run.status = RunStatus.FAILED
        run.finished_at = utc_now()
        run.error_message = truncate(error, 2000)
        await self._emit_run_changed(run, "run.failed")

    # ------------------------------------------------------------------

    async def log_tool_call(
        self,
        *,
        run: AgentRun,
        tool_name: str,
        status: str,
        args: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        requires_confirmation: bool = False,
        confirmation_id: uuid.UUID | None = None,
    ) -> ToolCall:
        call = ToolCall(
            agent_run_id=run.id,
            user_id=run.user_id,
            tool_name=tool_name,
            status=status,
            args_json=args or {},
            result_json=result,
            error_message=truncate(error, 1000) if error else None,
            requires_confirmation=requires_confirmation,
            confirmation_id=confirmation_id,
            started_at=utc_now(),
            finished_at=utc_now() if status in ("completed", "failed", "skipped") else None,
        )
        self.session.add(call)
        await self.session.flush()
        await RealtimeEventService(self.session).emit(
            user_id=run.user_id,
            topics=["runs"],
            event_type="tool_call.logged",
            payload={"run_id": str(run.id), "tool_call_id": str(call.id), "tool_name": tool_name},
        )
        return call

    async def _emit_run_changed(self, run: AgentRun, event_type: str) -> None:
        await RealtimeEventService(self.session).emit(
            user_id=run.user_id,
            topics=["runs"],
            event_type=event_type,
            payload={"run_id": str(run.id), "status": run.status.value},
        )
