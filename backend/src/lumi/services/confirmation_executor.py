"""Executes actions after the user explicitly confirms them."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.memory_service import MemoryService
from lumi.assistant.schemas import CalendarRequest, ExtractedTask, MemoryCandidate
from lumi.db.models import PendingConfirmation, TaskStatus, User
from lumi.i18n import normalize_app_locale
from lumi.logging import get_logger
from lumi.services.calendar import CalendarService
from lumi.services.task_update_fields import resolve_task_update_fields
from lumi.services.task_update_replies import format_task_bulk_update_reply, format_task_update_reply
from lumi.services.tasks import TaskService
from lumi.utils.time import fmt_local, local_to_utc

log = get_logger(__name__)
REMOVED_CONFIRMATION_ACTIONS = frozenset({
    "create_automation",
    "send_email",
    "delete_email",
    "archive_email",
})


class ConfirmationExecutor:
    """Maps accepted confirmation -> real action. Returns human text for the chat."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tasks = TaskService(session)
        self.memory = MemoryService(session)
        self.calendar = CalendarService(session)

    async def execute(self, user: User, confirmation: PendingConfirmation) -> str:
        locale = normalize_app_locale(user.locale)
        action = confirmation.action_type
        payload = confirmation.action_payload
        try:
            if action == "create_task":
                signal = ExtractedTask.model_validate(payload)
                created_task = await self.tasks.create_task_from_signal(user, signal)
                text = _text(
                    locale,
                    f"Created task: \"{created_task.title}\".",
                    f"Создал задачу: «{created_task.title}».",
                )
                if created_task.project:
                    text = _text(
                        locale,
                        f"Created task: \"{created_task.title}\" in project {created_task.project}.",
                        f"Создал задачу: «{created_task.title}» в проекте {created_task.project}.",
                    )
                if created_task.reminder_at:
                    text += _text(
                        locale,
                        f" Reminder {fmt_local(created_task.reminder_at, user.timezone)}.",
                        f" Напоминание {fmt_local(created_task.reminder_at, user.timezone)}.",
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
                task_to_update = await self.tasks.get(user, task_id)
                updates = payload.get("updates")
                reopens_done = (
                    isinstance(updates, dict)
                    and updates.get("status") == TaskStatus.ACTIVE.value
                )
                if task_to_update is None or (
                    task_to_update.status == TaskStatus.DONE and not reopens_done
                ):
                    return _text(
                        locale,
                        "This task is already done or deleted — there is nothing to update.",
                        "Эта задача уже закрыта или удалена — обновлять нечего.",
                    )
                if not isinstance(updates, dict) or not updates:
                    return _text(locale, "I didn't understand what to change in the task. Clarify the update.", "Не понял, что изменить в задаче. Уточни изменение.")
                raw_updates = updates
                updates = resolve_task_update_fields(user=user, task=task_to_update, updates=raw_updates)
                if not updates:
                    return _text(locale, "I didn't understand what to change in the task. Clarify the update.", "Не понял, что изменить в задаче. Уточни изменение.")
                agent_run_id = None
                if payload.get("agent_run_id"):
                    try:
                        agent_run_id = uuid.UUID(str(payload["agent_run_id"]))
                    except ValueError:
                        agent_run_id = None
                updated_task = await self.tasks.update_task(
                    user,
                    task_to_update,
                    updates,
                    actor="user",
                    agent_run_id=agent_run_id,
                )
                reply_updates = {
                    **updates,
                    **({"status": updated_task.status.value} if "status" in updates else {}),
                }
                return format_task_update_reply(
                    updated_task,
                    reply_updates,
                    language=str(payload.get("language") or locale),
                    timezone=user.timezone,
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

            if action == "create_google_calendar_event":
                calendar_request = CalendarRequest.model_validate(payload)
                from lumi.connectors.google.auth import GoogleNotConnectedError
                from lumi.connectors.google.calendar import GoogleCalendarConnector

                if not calendar_request.start_at_local or not calendar_request.end_at_local:
                    return _text(locale, "Start/end time is missing — please clarify.", "Не хватает времени начала/конца — уточни, пожалуйста.")
                start_utc = local_to_utc(calendar_request.start_at_local, user.timezone)
                end_utc = local_to_utc(calendar_request.end_at_local, user.timezone)
                try:
                    ref = await GoogleCalendarConnector().create_event(
                        title=calendar_request.title or "Событие от Lumi",
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
                    title=calendar_request.title or "Событие от Lumi",
                    start_at=start_utc,
                    end_at=end_utc,
                )
                title = calendar_request.title or _text(locale, "event", "событие")
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
