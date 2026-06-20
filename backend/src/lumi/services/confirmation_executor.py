"""Executes actions after the user explicitly confirms them."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.memory_service import MemoryService
from lumi.assistant.schemas import AutomationRequest, CalendarRequest, ExtractedTask, MemoryCandidate
from lumi.db.models import PendingConfirmation, TaskStatus, User
from lumi.i18n import normalize_app_locale
from lumi.logging import get_logger
from lumi.services.automations import AutomationService
from lumi.services.calendar import CalendarService
from lumi.services.task_update_replies import format_task_bulk_update_reply, format_task_update_reply
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
        locale = normalize_app_locale(user.locale)
        action = confirmation.action_type
        payload = confirmation.action_payload
        try:
            if action == "create_task":
                signal = ExtractedTask.model_validate(payload)
                task = await self.tasks.create_task_from_signal(user, signal)
                text = _text(locale, f"Created task: \"{task.title}\".", f"Создал задачу: «{task.title}».")
                if task.project:
                    text = _text(
                        locale,
                        f"Created task: \"{task.title}\" in project {task.project}.",
                        f"Создал задачу: «{task.title}» в проекте {task.project}.",
                    )
                if task.reminder_at:
                    text += _text(
                        locale,
                        f" Reminder {fmt_local(task.reminder_at, user.timezone)}.",
                        f" Напоминание {fmt_local(task.reminder_at, user.timezone)}.",
                    )
                return text

            if action == "store_memory":
                candidate = MemoryCandidate.model_validate(payload)
                memory, created = await self.memory.store_candidate(
                    user, candidate, actor="user"
                )
                if created:
                    return _text(locale, "Remembered.", "Запомнил.")
                return _text(locale, "Updated the existing note.", "Обновил существующую заметку.")

            if action == "update_task":
                try:
                    task_id = uuid.UUID(str(payload.get("task_id") or ""))
                except ValueError:
                    return _text(locale, "I couldn't find an active task. Clarify the title.", "Не нашёл активную задачу. Уточни название.")
                task = await self.tasks.get(user, task_id)
                if task is None or task.status == TaskStatus.DONE:
                    return _text(
                        locale,
                        "This task is already done or deleted — there is nothing to update.",
                        "Эта задача уже закрыта или удалена — обновлять нечего.",
                    )
                updates = payload.get("updates")
                if not isinstance(updates, dict) or not updates:
                    return _text(locale, "I didn't understand what to change in the task. Clarify the update.", "Не понял, что изменить в задаче. Уточни изменение.")
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
                    language=str(payload.get("language") or locale),
                )

            if action == "update_task_choice":
                return _text(locale, "Choose the task with the Telegram button.", "Выбери задачу кнопкой в Telegram.")

            if action == "bulk_update_tasks":
                raw_ids = payload.get("candidate_task_ids")
                if not isinstance(raw_ids, list) or not raw_ids:
                    return _text(locale, "I couldn't find matching tasks. Clarify the filter.", "Не нашёл подходящих задач. Уточни фильтр.")
                tasks = []
                for raw_id in raw_ids[:100]:
                    try:
                        task_id = uuid.UUID(str(raw_id))
                    except ValueError:
                        continue
                    task = await self.tasks.get(user, task_id)
                    if task is not None and task.status != TaskStatus.DONE:
                        tasks.append(task)
                if not tasks:
                    return _text(
                        locale,
                        "These tasks are already done or deleted — there is nothing to update.",
                        "Эти задачи уже закрыты или удалены — обновлять нечего.",
                    )
                updates = payload.get("updates")
                if not isinstance(updates, dict):
                    updates = {}
                tags_add = payload.get("tags_add")
                tags_remove = payload.get("tags_remove")
                if not isinstance(tags_add, list):
                    tags_add = None
                if not isinstance(tags_remove, list):
                    tags_remove = None
                if not updates and not tags_add and not tags_remove:
                    return _text(locale, "I didn't understand what to change in the tasks. Clarify the update.", "Не понял, что изменить в задачах. Уточни изменение.")
                agent_run_id = None
                if payload.get("agent_run_id"):
                    try:
                        agent_run_id = uuid.UUID(str(payload["agent_run_id"]))
                    except ValueError:
                        agent_run_id = None
                updated = await self.tasks.bulk_update_tasks(
                    user,
                    tasks,
                    updates,
                    tags_add=tags_add,
                    tags_remove=tags_remove,
                    actor="user",
                    agent_run_id=agent_run_id,
                )
                return format_task_bulk_update_reply(
                    len(updated),
                    updates,
                    tags_add=tags_add,
                    tags_remove=tags_remove,
                    language=str(payload.get("language") or locale),
                )

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
                return _text(
                    locale,
                    f"Automation \"{automation.title}\" is enabled ({automation.cron_expression}).",
                    f"Автоматизация «{automation.title}» включена ({automation.cron_expression}).",
                )

            if action == "create_google_calendar_event":
                request = CalendarRequest.model_validate(payload)
                from lumi.connectors.google.auth import GoogleNotConnectedError
                from lumi.connectors.google.calendar import GoogleCalendarConnector

                if not request.start_at_local or not request.end_at_local:
                    return _text(locale, "Start/end time is missing — please clarify.", "Не хватает времени начала/конца — уточни, пожалуйста.")
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
                    return _text(
                        locale,
                        "Google Calendar is not connected. Connect it with `make google-auth-local`, and I can create events.",
                        "Google Calendar не подключен. Подключи его через `make google-auth-local`, и я смогу записывать события.",
                    )
                await self.calendar.upsert_external_event(
                    user,
                    external_calendar_id=ref.external_calendar_id,
                    external_event_id=ref.external_event_id,
                    title=request.title or "Событие от Lumi",
                    start_at=start_utc,
                    end_at=end_utc,
                )
                title = request.title or _text(locale, "event", "событие")
                return _text(locale, f"Added \"{title}\" to Google Calendar.", f"Добавил «{title}» в Google Calendar.")

            log.warning("unknown confirmation action", fields={"action": action})
            return _text(locale, "I don't know how to perform this action yet.", "Это действие я пока не умею выполнять.")
        except Exception:  # noqa: BLE001
            log.exception("confirmation execution failed", fields={"action": action})
            return _text(
                locale,
                "I couldn't perform the action — try again or do it manually.",
                "Не получилось выполнить действие — попробуй еще раз или сделай вручную.",
            )


def _text(locale: str, en: str, ru: str) -> str:
    return en if locale == "en" else ru
