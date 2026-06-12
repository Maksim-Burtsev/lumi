"""Day planning: tasks + free slots -> LLM -> proposed focus blocks."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.prompts import DAILY_PLANNING_SYSTEM
from lumi.assistant.schemas import PlanResult
from lumi.db.models import CalendarEventStatus, User
from lumi.llm.base import LLMMessage
from lumi.llm.gateway import LLMGateway
from lumi.logging import get_logger
from lumi.services.calendar import CalendarService
from lumi.services.tasks import TaskService
from lumi.utils.time import fmt_local, local_to_utc, utc_now, utc_to_local

log = get_logger(__name__)


class PlanningService:
    def __init__(self, session: AsyncSession, *, llm: LLMGateway | None = None) -> None:
        self.session = session
        self.llm = llm or LLMGateway()
        self.calendar = CalendarService(session)
        self.tasks = TaskService(session)

    async def propose_day_plan(
        self, user: User, *, day: datetime | None = None, agent_run_id: uuid.UUID | None = None
    ) -> tuple[str, list]:
        """Returns (summary text, list of created proposed CalendarEvent)."""
        day = day or utc_now()
        # Re-planning replaces pending proposals — otherwise every run stacks
        # another layer of duplicate blocks on the same day.
        await self.calendar.cancel_proposed_blocks(user, day=day)
        free_slots = await self.calendar.find_free_slots(user, day=day, duration_minutes=45)
        active_tasks = await self.tasks.list_active(user, limit=25)

        if not free_slots:
            return ("Сегодня свободных окон не осталось — календарь плотный. "
                    "Могу поискать слоты на завтра."), []
        if not active_tasks:
            return ("Активных задач нет, так что план простой: можно спокойно работать "
                    "по календарю или добавить новые задачи."), []

        tz = user.timezone
        task_lines = []
        for t in active_tasks:
            line = f"- id={t.id} [{t.priority}] {t.title}"
            if t.due_at:
                line += f" (срок {fmt_local(t.due_at, tz)})"
            task_lines.append(line)
        slot_lines = [
            f"- {utc_to_local(s, tz).strftime('%H:%M')}–{utc_to_local(e, tz).strftime('%H:%M')}"
            for s, e in free_slots
        ]
        local_day = utc_to_local(day, tz)
        user_content = (
            f"Дата: {local_day.strftime('%Y-%m-%d')} ({tz})\n\n"
            f"Активные задачи:\n" + "\n".join(task_lines) +
            "\n\nСвободные окна сегодня:\n" + "\n".join(slot_lines)
        )

        raw = await self.llm.complete_json(
            messages=[LLMMessage(role="user", content=user_content)],
            system=DAILY_PLANNING_SYSTEM,
            request_kind="daily_planning",
            user_id=user.id,
            agent_run_id=agent_run_id,
            session=self.session,
        )
        try:
            plan = PlanResult.model_validate(raw)
        except Exception:  # noqa: BLE001
            log.warning("plan result failed validation")
            plan = PlanResult(summary="Не удалось собрать план автоматически.")

        created = []
        for block in plan.blocks[:3]:
            start_utc = local_to_utc(block.start_at_local, tz)
            end_utc = local_to_utc(block.end_at_local, tz)
            if end_utc <= start_utc:
                continue
            # Focus blocks are capped at 2 hours — long marathons get clipped.
            if end_utc - start_utc > timedelta(hours=2):
                end_utc = start_utc + timedelta(hours=2)
            task_id = None
            if block.task_id:
                try:
                    task_id = uuid.UUID(block.task_id)
                except ValueError:
                    task_id = None
            event = await self.calendar.create_internal_block(
                user,
                title=block.title,
                start_at=start_utc,
                end_at=end_utc,
                description=block.reason,
                status=CalendarEventStatus.PROPOSED,
                created_by="agent",
                source_task_id=task_id,
                agent_run_id=agent_run_id,
            )
            created.append(event)

        summary = plan.summary or "План готов."
        if created:
            lines = [
                f"• {utc_to_local(e.start_at, tz).strftime('%H:%M')}–"
                f"{utc_to_local(e.end_at, tz).strftime('%H:%M')} {e.title}"
                for e in created
            ]
            summary += "\n\nПредложенные блоки (ждут подтверждения):\n" + "\n".join(lines)
        return summary, created


class CalendarSyncService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.calendar = CalendarService(session)

    async def sync_google_calendar(self, user: User, *, days_ahead: int = 14) -> int:
        """Pull upcoming Google events into calendar_events. Raises GoogleNotConnectedError."""
        from lumi.connectors.google.calendar import GoogleCalendarConnector

        connector = GoogleCalendarConnector()
        start = utc_now() - timedelta(days=1)
        end = utc_now() + timedelta(days=days_ahead)
        dtos = await connector.list_events(start=start, end=end)
        synced = 0
        for dto in dtos:
            status = {
                "confirmed": CalendarEventStatus.CONFIRMED,
                "tentative": CalendarEventStatus.TENTATIVE,
            }.get(dto.status, CalendarEventStatus.CONFIRMED)
            await self.calendar.upsert_external_event(
                user,
                external_calendar_id=dto.external_calendar_id,
                external_event_id=dto.external_event_id,
                title=dto.title,
                start_at=dto.start_at,
                end_at=dto.end_at,
                description=dto.description,
                all_day=dto.all_day,
                busy=dto.busy,
                status=status,
            )
            synced += 1
        return synced

    async def sync_yandex_calendar(self, user: User, *, days_ahead: int = 14) -> int:
        """Pull upcoming Yandex (CalDAV) events. Raises YandexNotConnectedError."""
        from lumi.connectors.yandex.caldav_client import (
            get_yandex_connector_row,
            load_yandex_client,
        )
        from lumi.db.models import CalendarSource, ConnectorStatus

        client = await load_yandex_client(self.session, user)
        start = utc_now() - timedelta(days=1)
        end = utc_now() + timedelta(days=days_ahead)
        dtos = await client.list_events(start=start, end=end)
        synced = 0
        for dto in dtos:
            status = {
                "confirmed": CalendarEventStatus.CONFIRMED,
                "tentative": CalendarEventStatus.TENTATIVE,
                "cancelled": CalendarEventStatus.CANCELLED,
            }.get(dto.status, CalendarEventStatus.CONFIRMED)
            await self.calendar.upsert_external_event(
                user,
                source=CalendarSource.YANDEX,
                external_calendar_id=dto.external_calendar_id,
                external_event_id=dto.external_event_id,
                title=dto.title,
                start_at=dto.start_at,
                end_at=dto.end_at,
                description=dto.description,
                all_day=dto.all_day,
                busy=dto.busy,
                status=status,
            )
            synced += 1
        connector = await get_yandex_connector_row(self.session, user)
        if connector is not None:
            connector.last_sync_at = utc_now()
            connector.status = ConnectorStatus.CONNECTED
            connector.last_error = None
        return synced

    async def sync_all_calendars(self, user: User, *, days_ahead: int = 14) -> dict[str, int | str]:
        """Sync every configured external calendar. Raises only if NONE is configured."""
        from lumi.connectors.google.auth import GoogleNotConnectedError, token_file_exists
        from lumi.connectors.yandex.caldav_client import (
            YandexNotConnectedError,
            get_yandex_connector_row,
        )

        results: dict[str, int | str] = {}
        google_configured = token_file_exists()
        yandex_row = await get_yandex_connector_row(user=user, session=self.session)
        yandex_configured = yandex_row is not None and bool(yandex_row.credentials_encrypted)

        if not google_configured and not yandex_configured:
            raise GoogleNotConnectedError("ни один внешний календарь не подключен")

        if google_configured:
            try:
                results["google"] = await self.sync_google_calendar(user, days_ahead=days_ahead)
            except GoogleNotConnectedError as exc:
                results["google"] = f"error: {exc}"
        if yandex_configured:
            try:
                results["yandex"] = await self.sync_yandex_calendar(user, days_ahead=days_ahead)
            except YandexNotConnectedError as exc:
                results["yandex"] = f"error: {exc}"
                if yandex_row is not None:
                    from lumi.db.models import ConnectorStatus

                    yandex_row.status = ConnectorStatus.NEEDS_REAUTH
                    yandex_row.last_error = str(exc)[:500]
        return results
