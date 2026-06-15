"""Executes actions after the user explicitly confirms them."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.memory_service import MemoryService
from lumi.assistant.schemas import AutomationRequest, CalendarRequest, ExtractedTask, MemoryCandidate
from lumi.db.models import PendingConfirmation, TaskStatus, User
from lumi.logging import get_logger
from lumi.services.automations import AutomationService
from lumi.services.calendar import CalendarService
from lumi.services.task_update_replies import format_task_update_reply
from lumi.services.tasks import TaskService
from lumi.utils.time import fmt_local, local_to_utc

log = get_logger(__name__)


class ConfirmationExecutor:
    """Maps accepted confirmation -> real action. Returns human text for the chat."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tasks = TaskService(session)
        self.memory = MemoryService(session)
        self.calendar = CalendarService(session)
        self.automations = AutomationService(session)

    async def execute(self, user: User, confirmation: PendingConfirmation) -> str:
        action = confirmation.action_type
        payload = confirmation.action_payload
        try:
            if action == "create_task":
                signal = ExtractedTask.model_validate(payload)
                task = await self.tasks.create_task_from_signal(user, signal)
                text = f"Создал задачу: «{task.title}»."
                if task.reminder_at:
                    text += f" Напоминание {fmt_local(task.reminder_at, user.timezone)}."
                return text

            if action == "store_memory":
                candidate = MemoryCandidate.model_validate(payload)
                memory, created = await self.memory.store_candidate(
                    user, candidate, actor="user"
                )
                return "Запомнил." if created else "Обновил существующую заметку."

            if action == "update_task":
                try:
                    task_id = uuid.UUID(str(payload.get("task_id") or ""))
                except ValueError:
                    return "Не нашёл активную задачу. Уточни название."
                task = await self.tasks.get(user, task_id)
                if task is None or task.status == TaskStatus.DONE:
                    return "Эта задача уже закрыта или удалена — обновлять нечего."
                updates = payload.get("updates")
                if not isinstance(updates, dict) or not updates:
                    return "Не понял, что изменить в задаче. Уточни изменение."
                agent_run_id = None
                if payload.get("agent_run_id"):
                    try:
                        agent_run_id = uuid.UUID(str(payload["agent_run_id"]))
                    except ValueError:
                        agent_run_id = None
                task = await self.tasks.update_task(
                    user,
                    task,
                    updates,
                    actor="user",
                    agent_run_id=agent_run_id,
                )
                return format_task_update_reply(
                    task,
                    updates,
                    language=str(payload.get("language") or ""),
                )

            if action == "update_task_choice":
                return "Выбери задачу кнопкой в Telegram."

            if action == "create_automation":
                request = AutomationRequest.model_validate(payload)
                automation = await self.automations.create(
                    user,
                    type_=request.type,
                    title=request.title,
                    cron_expression=request.cron_expression or "30 8 * * 1-5",
                    timezone=request.timezone,
                    config=request.config,
                    enabled=True,
                )
                return f"Автоматизация «{automation.title}» включена ({automation.cron_expression})."

            if action == "create_google_calendar_event":
                request = CalendarRequest.model_validate(payload)
                from lumi.connectors.google.auth import GoogleNotConnectedError
                from lumi.connectors.google.calendar import GoogleCalendarConnector

                if not request.start_at_local or not request.end_at_local:
                    return "Не хватает времени начала/конца — уточни, пожалуйста."
                start_utc = local_to_utc(request.start_at_local, user.timezone)
                end_utc = local_to_utc(request.end_at_local, user.timezone)
                try:
                    ref = await GoogleCalendarConnector().create_event(
                        title=request.title or "Событие от Lumi",
                        start_at=start_utc,
                        end_at=end_utc,
                        timezone=user.timezone,
                    )
                except GoogleNotConnectedError:
                    return ("Google Calendar не подключен. Подключи его через "
                            "`make google-auth-local`, и я смогу записывать события.")
                await self.calendar.upsert_external_event(
                    user,
                    external_calendar_id=ref.external_calendar_id,
                    external_event_id=ref.external_event_id,
                    title=request.title or "Событие от Lumi",
                    start_at=start_utc,
                    end_at=end_utc,
                )
                return f"Добавил «{request.title or 'событие'}» в Google Calendar."

            log.warning("unknown confirmation action", fields={"action": action})
            return "Это действие я пока не умею выполнять."
        except Exception:  # noqa: BLE001
            log.exception("confirmation execution failed", fields={"action": action})
            return "Не получилось выполнить действие — попробуй еще раз или сделай вручную."
