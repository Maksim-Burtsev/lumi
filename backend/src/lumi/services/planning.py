"""Day planning: tasks + free slots -> LLM -> proposed focus blocks."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.prompts import DAILY_PLANNING_SYSTEM
from lumi.assistant.schemas import PlannedBlock, PlanResult
from lumi.config import get_settings
from lumi.db.models import (
    CalendarEvent,
    CalendarEventStatus,
    CalendarSource,
    Connector,
    ConnectorStatus,
    ConnectorType,
    PlanningRequest,
    Task,
    TaskStatus,
    User,
)
from lumi.i18n import normalize_app_locale
from lumi.llm.base import LLMMessage
from lumi.llm.gateway import LLMGateway
from lumi.logging import get_logger
from lumi.services.calendar import (
    MEETING_BUFFER,
    CalendarService,
    _planning_proposal_expired,
)
from lumi.services.planning_settings import (
    normalize_planning_settings,
    planning_work_window,
)
from lumi.services.tasks import TaskService
from lumi.services.work_blocks import WorkBlockResultStatus, WorkBlockService
from lumi.utils.time import fmt_local, get_zone, local_to_utc, utc_now, utc_to_local

log = get_logger(__name__)
PlanningMode = Literal["today", "tomorrow", "replan"]
MIN_PLAN_BLOCK_MINUTES = 15
MAX_PLAN_BLOCK_MINUTES = 240
PROPOSAL_TTL = timedelta(hours=2)


def _planning_text(user: User, *, en: str, ru: str) -> str:
    return ru if normalize_app_locale(user.locale) == "ru" else en


def next_planning_workday(user: User, *, now: datetime | None = None) -> datetime:
    """Return local noon on the next configured workday."""
    local = utc_to_local(now or utc_now(), user.timezone)
    work_days = set(normalize_planning_settings(user.settings)["work_days"])
    for offset in range(1, 8):
        candidate = local + timedelta(days=offset)
        if candidate.weekday() in work_days:
            return candidate.replace(hour=12, minute=0, second=0, microsecond=0)
    return (local + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)


def resolve_plan_day(
    user: User,
    *,
    mode: PlanningMode,
    day: datetime | None = None,
    now: datetime | None = None,
) -> datetime:
    current = now or utc_now()
    if mode == "replan":
        return utc_to_local(current, user.timezone)
    if day is not None:
        return day
    if mode == "tomorrow":
        return next_planning_workday(user, now=current)
    return utc_to_local(current, user.timezone)


def _proposal_expiry(user: User, day: datetime, *, now: datetime) -> datetime:
    work_window = planning_work_window(user.settings, day, user.timezone)
    if work_window is None:
        return now + PROPOSAL_TTL
    window_start, window_end = work_window
    # A plan for tomorrow remains actionable through the beginning of that
    # workday. A plan for today gets the same short freshness window.
    if window_start > now:
        return min(window_end, window_start + PROPOSAL_TTL)
    return min(window_end, now + PROPOSAL_TTL)


def _planning_context_hash(
    *,
    task_ids: list[uuid.UUID],
    free_slots: list[tuple[datetime, datetime]],
) -> str:
    payload = "|".join(
        [*(str(task_id) for task_id in sorted(task_ids, key=str))]
        + [
            f"{start.isoformat()}:{end.isoformat()}"
            for start, end in free_slots
        ]
    )
    return sha256(payload.encode()).hexdigest()


def _local_candidate_roundtrips(value: datetime, timezone: str) -> bool:
    zone = get_zone(timezone)
    if value.tzinfo is not None:
        expected = value.astimezone(zone).replace(tzinfo=None)
    else:
        expected = value
        fold_zero = value.replace(tzinfo=zone, fold=0).utcoffset()
        fold_one = value.replace(tzinfo=zone, fold=1).utcoffset()
        if fold_zero != fold_one:
            return False
    converted = local_to_utc(value, timezone)
    return utc_to_local(converted, timezone).replace(tzinfo=None) == expected


class PlanningService:
    def __init__(self, session: AsyncSession, *, llm: LLMGateway | None = None) -> None:
        self.session = session
        self.llm = llm or LLMGateway()
        self.calendar = CalendarService(session)
        self.tasks = TaskService(session)
        self.work_blocks = WorkBlockService(session)

    async def propose_day_plan(
        self,
        user: User,
        *,
        day: datetime | None = None,
        mode: PlanningMode = "today",
        request_id: str | None = None,
        agent_run_id: uuid.UUID | None = None,
    ) -> tuple[str, list]:
        """Returns (summary text, list of created proposed CalendarEvent)."""
        now = utc_now()
        day = resolve_plan_day(user, mode=mode, day=day, now=now)
        clean_request_id = (request_id or "").strip()[:120] or None
        batch_id = clean_request_id or str(agent_run_id or uuid.uuid4())
        request_key = (
            clean_request_id
            or (f"agent-run:{agent_run_id}" if agent_run_id is not None else None)
        )
        if request_key is not None:
            completed = await self._completed_request(user, request_key)
            if completed is not None:
                return await self._completed_request_result(user, completed)

        free_slots = await self.calendar.find_free_slots(
            user,
            day=day,
            duration_minutes=MIN_PLAN_BLOCK_MINUTES,
            ignore_future_planning_proposals=mode == "replan",
        )
        active_tasks = await self.tasks.list_active(user, limit=25)

        if not free_slots:
            summary = _planning_text(
                user,
                en=(
                    "No free windows remain in this workday; "
                    "existing calendar items stay unchanged."
                ),
                ru=(
                    "В этом рабочем дне не осталось свободных окон; "
                    "календарь не изменён."
                ),
            )
            return await self._record_empty_request(
                user,
                request_key=request_key,
                mode=mode,
                day=day,
                summary=summary,
            )
        if not active_tasks:
            summary = _planning_text(
                user,
                en=(
                    "There are no active tasks, so the plan is simple: "
                    "follow the calendar or add new tasks."
                ),
                ru=(
                    "Активных задач нет: можно следовать календарю "
                    "или сначала добавить задачи."
                ),
            )
            return await self._record_empty_request(
                user,
                request_key=request_key,
                mode=mode,
                day=day,
                summary=summary,
            )

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
            "\n\nFree windows for this date:\n" + "\n".join(slot_lines)
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
            plan = PlanResult()

        # The provider call happens before taking the per-user write lock. Once
        # it returns, re-read every mutable input and validate again while
        # calendar writers for this user are serialized.
        await self.session.execute(
            select(User.id).where(User.id == user.id).with_for_update()
        )
        if request_key is not None:
            completed = await self._completed_request(user, request_key)
            if completed is not None:
                return await self._completed_request_result(user, completed)
        await self._expire_stale_proposals(user, now=utc_now())
        free_slots = await self.calendar.find_free_slots(
            user,
            day=day,
            duration_minutes=MIN_PLAN_BLOCK_MINUTES,
            ignore_future_planning_proposals=mode == "replan",
        )
        active_tasks = await self.tasks.list_active(user, limit=25)
        tasks_by_id = {task.id: task for task in active_tasks}
        validated_blocks: list[
            tuple[PlannedBlock, uuid.UUID, datetime, datetime]
        ] = []
        accepted_intervals: list[tuple[datetime, datetime]] = []
        accepted_task_ids: set[uuid.UUID] = set()
        expires_at = _proposal_expiry(user, day, now=utc_now())
        context_hash = _planning_context_hash(
            task_ids=list(tasks_by_id),
            free_slots=free_slots,
        )
        for block in plan.blocks[:3]:
            if not (
                _local_candidate_roundtrips(block.start_at_local, tz)
                and _local_candidate_roundtrips(block.end_at_local, tz)
            ):
                continue
            start_utc = local_to_utc(block.start_at_local, tz)
            end_utc = local_to_utc(block.end_at_local, tz)
            try:
                task_id = uuid.UUID(block.task_id) if block.task_id else None
            except ValueError:
                continue
            if task_id is None or task_id not in tasks_by_id or task_id in accepted_task_ids:
                continue
            task = tasks_by_id[task_id]
            duration = end_utc - start_utc
            if (
                duration < timedelta(minutes=MIN_PLAN_BLOCK_MINUTES)
                or duration > timedelta(minutes=MAX_PLAN_BLOCK_MINUTES)
                or not any(
                    slot_start <= start_utc and end_utc <= slot_end
                    for slot_start, slot_end in free_slots
                )
                or any(
                    start_utc < accepted_end + MEETING_BUFFER
                    and end_utc > accepted_start - MEETING_BUFFER
                    for accepted_start, accepted_end in accepted_intervals
                )
                or (task.due_at is not None and end_utc > task.due_at)
            ):
                continue
            validated_blocks.append((block, task_id, start_utc, end_utc))
            accepted_intervals.append((start_utc, end_utc))
            accepted_task_ids.add(task_id)

        if validated_blocks:
            locked_tasks_result = await self.session.execute(
                select(Task)
                .where(
                    Task.user_id == user.id,
                    Task.id.in_([item[1] for item in validated_blocks]),
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            locked_tasks = {
                task.id: task for task in locked_tasks_result.scalars()
            }
            validated_blocks = [
                item
                for item in validated_blocks
                if (
                    (locked_task := locked_tasks.get(item[1])) is not None
                    and locked_task.status in {TaskStatus.INBOX, TaskStatus.ACTIVE}
                    and (
                        locked_task.due_at is None
                        or item[3] <= locked_task.due_at
                    )
                )
            ]

        if not validated_blocks:
            summary = _planning_text(
                user,
                en=(
                    "No safe blocks matched the current tasks, deadlines "
                    "and free calendar windows."
                ),
                ru=(
                    "Не нашлось безопасных блоков, подходящих текущим задачам, "
                    "дедлайнам и свободным окнам."
                ),
            )
            await self._record_request(
                user,
                request_key=request_key,
                mode=mode,
                day=day,
                summary=summary,
                events=[],
            )
            return summary, []

        # Only a validated replacement may remove future proposals. Provider
        # errors and empty/invalid output leave the existing plan untouched.
        if mode == "replan":
            await self.calendar.cancel_proposed_blocks(
                user,
                day=day,
                future_only=True,
                planning_only=True,
                now=now,
            )

        created: list[CalendarEvent] = []
        for block, task_id, start_utc, end_utc in validated_blocks:
            result = await self.work_blocks.create(
                user,
                task_id=task_id,
                title=block.title,
                start_at=start_utc,
                end_at=end_utc,
                description=block.reason,
                status=CalendarEventStatus.PROPOSED,
                created_by="agent",
                agent_run_id=agent_run_id,
                metadata={
                    "plan_batch_id": batch_id,
                    "planning_request_id": clean_request_id,
                    "planning_mode": mode,
                    "planning_context_hash": context_hash,
                    "proposal_expires_at": expires_at.isoformat(),
                },
            )
            if result.status == WorkBlockResultStatus.PROPOSED and result.event is not None:
                created.append(result.event)

        if not created:
            # This can happen only if the final domain checks observe a task
            # mutation. Do not claim success or create an idempotency result.
            return _planning_text(
                user,
                en="The calendar changed before the plan could be saved. Please replan.",
                ru="Календарь изменился до сохранения плана. Запусти планирование ещё раз.",
            ), []
        summary = plan.summary or _planning_text(
            user,
            en="Plan ready.",
            ru="План готов.",
        )
        lines = [
            f"• {utc_to_local(event.start_at, tz).strftime('%H:%M')}–"
            f"{utc_to_local(event.end_at, tz).strftime('%H:%M')} {event.title}"
            for event in created
        ]
        heading = _planning_text(
            user,
            en="Proposed blocks (waiting for confirmation):",
            ru="Предложенные блоки (ждут подтверждения):",
        )
        summary += f"\n\n{heading}\n" + "\n".join(lines)
        await self._record_request(
            user,
            request_key=request_key,
            mode=mode,
            day=day,
            summary=summary,
            events=created,
        )
        return summary, created

    async def _completed_request(
        self,
        user: User,
        request_key: str,
    ) -> PlanningRequest | None:
        return await self.session.scalar(
            select(PlanningRequest).where(
                PlanningRequest.user_id == user.id,
                PlanningRequest.request_key == request_key,
            )
        )

    async def _completed_request_result(
        self,
        user: User,
        request: PlanningRequest,
    ) -> tuple[str, list[CalendarEvent]]:
        event_ids: list[uuid.UUID] = []
        for value in request.event_ids:
            try:
                event_ids.append(uuid.UUID(value))
            except (TypeError, ValueError):
                continue
        if not event_ids:
            return request.summary, []
        result = await self.session.execute(
            select(CalendarEvent)
            .where(
                CalendarEvent.user_id == user.id,
                CalendarEvent.id.in_(event_ids),
                CalendarEvent.status == CalendarEventStatus.PROPOSED,
            )
            .order_by(CalendarEvent.start_at, CalendarEvent.id)
        )
        now = utc_now()
        events = [
            event
            for event in result.scalars()
            if not _planning_proposal_expired(event, now=now)
        ]
        if events:
            return self._existing_summary(events, user), events
        return _planning_text(
            user,
            en="This planning request was already processed.",
            ru="Этот запрос на планирование уже обработан.",
        ), []

    async def _record_request(
        self,
        user: User,
        *,
        request_key: str | None,
        mode: PlanningMode,
        day: datetime,
        summary: str,
        events: list[CalendarEvent],
    ) -> None:
        if request_key is None:
            return
        self.session.add(PlanningRequest(
            user_id=user.id,
            request_key=request_key,
            mode=mode,
            day_local=utc_to_local(day, user.timezone).date(),
            summary=summary,
            event_ids=[str(event.id) for event in events],
        ))
        await self.session.flush()

    async def _record_empty_request(
        self,
        user: User,
        *,
        request_key: str | None,
        mode: PlanningMode,
        day: datetime,
        summary: str,
    ) -> tuple[str, list[CalendarEvent]]:
        if request_key is None:
            return summary, []
        await self.session.execute(
            select(User.id).where(User.id == user.id).with_for_update()
        )
        completed = await self._completed_request(user, request_key)
        if completed is not None:
            return await self._completed_request_result(user, completed)
        await self._record_request(
            user,
            request_key=request_key,
            mode=mode,
            day=day,
            summary=summary,
            events=[],
        )
        return summary, []

    async def _expire_stale_proposals(self, user: User, *, now: datetime) -> int:
        result = await self.session.execute(
            select(CalendarEvent).where(
                CalendarEvent.user_id == user.id,
                CalendarEvent.source == CalendarSource.INTERNAL,
                CalendarEvent.status == CalendarEventStatus.PROPOSED,
                CalendarEvent.source_task_id.is_not(None),
            )
        )
        expired = 0
        for event in result.scalars():
            raw_expiry = (event.metadata_ or {}).get("proposal_expires_at")
            if not isinstance(raw_expiry, str):
                continue
            try:
                expires_at = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
            except ValueError:
                continue
            if (
                expires_at.tzinfo is not None
                and expires_at.utcoffset() is not None
                and expires_at <= now
            ):
                event.status = CalendarEventStatus.CANCELLED
                expired += 1
        return expired

    @staticmethod
    def _existing_summary(events: list[CalendarEvent], user: User) -> str:
        lines = [
            f"• {utc_to_local(event.start_at, user.timezone).strftime('%H:%M')}–"
            f"{utc_to_local(event.end_at, user.timezone).strftime('%H:%M')} {event.title}"
            for event in events
        ]
        heading = _planning_text(
            user,
            en="Plan already queued for this request:",
            ru="План по этому запросу уже предложен:",
        )
        return heading + "\n" + "\n".join(lines)


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
                watch_expires_at = datetime.fromisoformat(expires_at_raw)
                if watch_expires_at.tzinfo is None:
                    watch_expires_at = watch_expires_at.replace(tzinfo=_UTC)
                if watch_expires_at - utc_now() > timedelta(days=1):
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
        expires_at: datetime | None = None
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
