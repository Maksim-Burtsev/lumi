"""Day planning: tasks + free slots -> LLM -> proposed focus blocks."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.prompts import DAILY_PLANNING_SYSTEM
from lumi.assistant.schemas import PlanResult
from lumi.config import get_settings
from lumi.db.models import (
    CalendarEventStatus,
    CalendarSource,
    Connector,
    ConnectorStatus,
    ConnectorType,
    User,
)
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
            return ("No free windows remain today; the calendar is packed. "
                    "I can look for slots tomorrow."), []
        if not active_tasks:
            return ("There are no active tasks, so the plan is simple: follow the calendar "
                    "or add new tasks."), []

        tz = user.timezone
        task_lines = []
        for t in active_tasks:
            line = f"- id={t.id} [{t.priority}] {t.title}"
            if t.due_at:
                line += f" (due {fmt_local(t.due_at, tz)})"
            task_lines.append(line)
        slot_lines = [
            f"- {utc_to_local(s, tz).strftime('%H:%M')}–{utc_to_local(e, tz).strftime('%H:%M')}"
            for s, e in free_slots
        ]
        local_day = utc_to_local(day, tz)
        user_content = (
            f"Target language: {user.locale or 'en'}\n"
            f"Date: {local_day.strftime('%Y-%m-%d')} ({tz})\n\n"
            f"Active tasks:\n" + "\n".join(task_lines) +
            "\n\nFree windows today:\n" + "\n".join(slot_lines)
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
            plan = PlanResult(summary="Could not build the plan automatically.")

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

        summary = plan.summary or "Plan ready."
        if created:
            lines = [
                f"• {utc_to_local(e.start_at, tz).strftime('%H:%M')}–"
                f"{utc_to_local(e.end_at, tz).strftime('%H:%M')} {e.title}"
                for e in created
            ]
            summary += "\n\nProposed blocks (waiting for confirmation):\n" + "\n".join(lines)
        return summary, created


class CalendarSyncService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.calendar = CalendarService(session)

    @staticmethod
    def _sync_window(
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        days_ahead: int | None = None,
        days_back: int | None = None,
    ) -> tuple[datetime, datetime]:
        settings = get_settings()
        start = start_at or (
            utc_now() - timedelta(days=days_back if days_back is not None else settings.calendar_sync_days_back)
        )
        end = end_at or (
            utc_now() + timedelta(days=days_ahead if days_ahead is not None else settings.calendar_sync_days_ahead)
        )
        return start, end

    async def sync_google_calendar(
        self,
        user: User,
        *,
        days_ahead: int | None = None,
        days_back: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> int:
        """Pull upcoming Google events into calendar_events. Raises GoogleNotConnectedError."""
        from lumi.connectors.google.calendar import GoogleCalendarConnector

        connector = GoogleCalendarConnector()
        start, end = self._sync_window(
            start_at=start_at,
            end_at=end_at,
            days_ahead=days_ahead,
            days_back=days_back,
        )
        dtos = await connector.list_events(start=start, end=end)
        synced = 0
        seen_by_calendar: dict[str, set[str]] = defaultdict(set)
        for dto in dtos:
            status = {
                "confirmed": CalendarEventStatus.CONFIRMED,
                "tentative": CalendarEventStatus.TENTATIVE,
                "cancelled": CalendarEventStatus.CANCELLED,
            }.get(dto.status, CalendarEventStatus.CONFIRMED)
            seen_by_calendar[dto.external_calendar_id].add(dto.external_event_id)
            await self.calendar.upsert_external_event(
                user,
                source=CalendarSource.GOOGLE,
                external_calendar_id=dto.external_calendar_id,
                external_event_id=dto.external_event_id,
                title=dto.title,
                start_at=dto.start_at,
                end_at=dto.end_at,
                description=dto.description,
                all_day=dto.all_day,
                busy=dto.busy,
                status=status,
                location=dto.location,
                meeting_url=dto.meeting_url,
                external_url=dto.external_url,
                links=dto.links,
                external_updated_at=dto.external_updated_at,
                creator=dto.creator,
                organizer=dto.organizer,
                attendees=dto.attendees,
                user_response_status=dto.user_response_status,
            )
            synced += 1
        cancelled = 0
        known_calendar_ids = await self.calendar.external_calendar_ids_in_window(
            user, source=CalendarSource.GOOGLE, start_at=start, end_at=end
        )
        calendar_ids = set(seen_by_calendar) | known_calendar_ids | {"primary"}
        for calendar_id in calendar_ids:
            cancelled += await self.calendar.reconcile_external_events(
                user,
                source=CalendarSource.GOOGLE,
                external_calendar_id=calendar_id,
                start_at=start,
                end_at=end,
                seen_event_ids=seen_by_calendar.get(calendar_id, set()),
            )
        connector_row = await self._get_connector(user, ConnectorType.GOOGLE, create=True)
        if connector_row is not None:
            connector_row.last_sync_at = utc_now()
            connector_row.status = ConnectorStatus.CONNECTED
            connector_row.last_error = None
            await self._ensure_google_watch(user, connector_row)
        return synced + cancelled

    async def sync_yandex_calendar(
        self,
        user: User,
        *,
        days_ahead: int | None = None,
        days_back: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> int:
        """Pull upcoming Yandex (CalDAV) events. Raises YandexNotConnectedError."""
        from lumi.connectors.yandex.caldav_client import (
            get_yandex_connector_row,
            load_yandex_client,
        )

        client = await load_yandex_client(self.session, user)
        start, end = self._sync_window(
            start_at=start_at,
            end_at=end_at,
            days_ahead=days_ahead,
            days_back=days_back,
        )
        dtos = await client.list_events(start=start, end=end)
        synced = 0
        seen_by_calendar: dict[str, set[str]] = defaultdict(set)
        for dto in dtos:
            status = {
                "confirmed": CalendarEventStatus.CONFIRMED,
                "tentative": CalendarEventStatus.TENTATIVE,
                "cancelled": CalendarEventStatus.CANCELLED,
            }.get(dto.status, CalendarEventStatus.CONFIRMED)
            seen_by_calendar[dto.external_calendar_id].add(dto.external_event_id)
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
                location=dto.location,
                meeting_url=dto.meeting_url,
                external_url=dto.external_url,
                links=dto.links,
                organizer=dto.organizer,
                attendees=dto.attendees,
            )
            synced += 1
        cancelled = 0
        known_calendar_ids = await self.calendar.external_calendar_ids_in_window(
            user, source=CalendarSource.YANDEX, start_at=start, end_at=end
        )
        for calendar_id in set(seen_by_calendar) | known_calendar_ids:
            cancelled += await self.calendar.reconcile_external_events(
                user,
                source=CalendarSource.YANDEX,
                external_calendar_id=calendar_id,
                start_at=start,
                end_at=end,
                seen_event_ids=seen_by_calendar.get(calendar_id, set()),
            )
        connector = await get_yandex_connector_row(self.session, user)
        if connector is not None:
            connector.last_sync_at = utc_now()
            connector.status = ConnectorStatus.CONNECTED
            connector.last_error = None
        return synced + cancelled

    async def sync_all_calendars(
        self,
        user: User,
        *,
        days_ahead: int | None = None,
        days_back: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> dict[str, int | str]:
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

        from lumi.services.automations import AutomationService

        await AutomationService(self.session).ensure_system_calendar_sync(user)

        if google_configured:
            try:
                results["google"] = await self.sync_google_calendar(
                    user,
                    days_ahead=days_ahead,
                    days_back=days_back,
                    start_at=start_at,
                    end_at=end_at,
                )
            except GoogleNotConnectedError as exc:
                results["google"] = f"error: {exc}"
        if yandex_configured:
            try:
                results["yandex"] = await self.sync_yandex_calendar(
                    user,
                    days_ahead=days_ahead,
                    days_back=days_back,
                    start_at=start_at,
                    end_at=end_at,
                )
            except YandexNotConnectedError as exc:
                results["yandex"] = f"error: {exc}"
                if yandex_row is not None:
                    from lumi.db.models import ConnectorStatus

                    yandex_row.status = ConnectorStatus.NEEDS_REAUTH
                    yandex_row.last_error = str(exc)[:500]
        return results

    async def _get_connector(
        self, user: User, type_: ConnectorType, *, create: bool = False
    ) -> Connector | None:
        result = await self.session.execute(
            select(Connector).where(Connector.user_id == user.id, Connector.type == type_)
        )
        connector = result.scalar_one_or_none()
        if connector is None and create:
            connector = Connector(user_id=user.id, type=type_)
            self.session.add(connector)
            await self.session.flush()
        return connector

    async def _ensure_google_watch(self, user: User, connector: Connector) -> None:
        import secrets
        from datetime import UTC as _UTC

        from lumi.config import get_settings
        from lumi.connectors.google.calendar import GoogleCalendarConnector

        settings = get_settings()
        if not settings.app_public_url:
            return
        metadata = connector.metadata_ or {}
        watch = metadata.get("calendar_watch") or {}
        expires_at_raw = watch.get("expires_at")
        if expires_at_raw:
            try:
                expires_at = datetime.fromisoformat(expires_at_raw)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=_UTC)
                if expires_at - utc_now() > timedelta(days=1):
                    return
            except ValueError:
                pass

        channel_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(24)
        address = settings.app_public_url.rstrip("/") + "/api/connectors/google/webhook"
        try:
            response = await GoogleCalendarConnector().watch_events(
                address=address,
                channel_id=channel_id,
                token=token,
            )
        except Exception as exc:  # noqa: BLE001 - sync itself must not fail on watch setup
            connector.metadata_ = {**metadata, "calendar_watch_error": str(exc)[:500]}
            return
        expires_at = None
        expiration_ms = response.get("expiration")
        if expiration_ms:
            try:
                expires_at = datetime.fromtimestamp(int(expiration_ms) / 1000, tz=_UTC)
            except (TypeError, ValueError):
                expires_at = None
        connector.metadata_ = {
            **metadata,
            "calendar_watch": {
                "channel_id": response.get("id", channel_id),
                "resource_id": response.get("resourceId"),
                "token": token,
                "calendar_id": "primary",
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
            "calendar_watch_error": None,
        }
