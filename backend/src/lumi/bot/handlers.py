"""aiogram handlers: commands, chat messages, callback confirmations."""

from __future__ import annotations

import uuid

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery
from aiogram.types import Message as TgMessage

from lumi.bot.formatting import HELP_TEXT, format_tasks, format_today, telegram_plain_text
from lumi.bot.keyboards import mini_app_button, start_keyboard
from lumi.bot.media import (
    AttachmentBatchBuffer,
    build_logical_message,
    classify_attachment_message,
    extract_image_ref,
)
from lumi.bot.schedule_messages import render_today_schedule
from lumi.config import get_settings
from lumi.db.models import CalendarEventStatus, ConfirmationStatus, Message, MessageRole
from lumi.db.session import session_scope
from lumi.i18n import ensure_language_settings, normalize_reply_language
from lumi.logging import get_logger, telegram_update_id_var
from lumi.services.confirmation_executor import ConfirmationExecutor
from lumi.services.confirmations import ConfirmationService
from lumi.services.realtime import commit_with_realtime
from lumi.services.runs import RunService
from lumi.services.task_update_replies import format_task_update_reply
from lumi.services.tasks import TaskService
from lumi.services.today import TodayService
from lumi.services.turns import TelegramIntakeService, TurnService
from lumi.services.users import UserService
from lumi.utils.text import chunk_telegram
from lumi.worker.jobs import AGENT_RUN_TYPE_BY_AUTOMATION, JOB_BY_AUTOMATION_TYPE
from lumi.worker.queue import enqueue_job, get_queue

log = get_logger(__name__)
router = Router(name="lumi")
REJECTED_ATTACHMENT_REPLY = (
    "Не обрабатываю сообщения с несколькими картинками или неподдерживаемыми вложениями. "
    "Пришли одно изображение JPEG/PNG/WEBP до 10 MB без других файлов."
)


def _deadline_job_id(turn_id: uuid.UUID, enqueue_at) -> str:
    return f"assistant-turn:{turn_id}:at:{int(enqueue_at.timestamp() * 1000)}"


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

def _is_owner(telegram_user_id: int) -> bool:
    return telegram_user_id in get_settings().allowed_telegram_user_ids


def _language_code(event: TgMessage | CallbackQuery) -> str | None:
    return getattr(event.from_user, "language_code", None) if event.from_user else None


def _text_for_language(language: str | None, *, en: str, ru: str, it: str | None = None) -> str:
    primary = normalize_reply_language(language)
    if primary == "ru":
        return ru
    if primary == "it":
        return it or en
    return en


def _reply_language_for_message(user, language_code: str | None = None) -> str:
    settings = ensure_language_settings(user.settings)
    mode = settings.get("reply_language_mode")
    if mode == "fixed":
        return normalize_reply_language(str(settings.get("reply_language") or "en"))
    if mode == "app_locale":
        return normalize_reply_language(user.locale)
    return normalize_reply_language(language_code or user.language_code or user.locale)


def _reply_language_for_callback(user, language_code: str | None = None) -> str:
    return _reply_language_for_message(user, language_code)


def _block_confirm_missing_text(language: str | None) -> str:
    return _text_for_language(
        language,
        en="Block not found or already confirmed",
        ru="Блок не найден или уже подтвержден",
        it="Blocco non trovato o gia confermato",
    )


def _block_confirm_accepted_text(language: str | None) -> str:
    return _text_for_language(
        language,
        en="Accepted",
        ru="Принято",
        it="Accettato",
    )


def _block_confirmed_text(
    language: str | None,
    *,
    title: str,
    start_label: str,
    end_label: str,
) -> str:
    return _text_for_language(
        language,
        en=f"✓ Focus block in calendar: {title}, {start_label}–{end_label}",
        ru=f"✓ Фокус-блок в календаре: {title}, {start_label}–{end_label}",
        it=f"✓ Blocco focus in calendario: {title}, {start_label}–{end_label}",
    )


async def _check_allowed(event: TgMessage | CallbackQuery) -> bool:
    """Owners come from env; everyone else must be approved (users.is_allowed)."""
    tg_user = event.from_user
    if tg_user is None:
        return False
    if isinstance(event, TgMessage) and event.chat.type != "private":
        return False
    if _is_owner(tg_user.id):
        return True
    async with session_scope() as session:
        user = await UserService(session).get_by_telegram_id(tg_user.id)
        if user is not None and user.is_allowed:
            return True
    if get_settings().log_unauthorized_telegram_ids:
        log.warning("unauthorized telegram user",
                    fields={"telegram_user_id": tg_user.id, "username": tg_user.username})
    return False


async def _request_access(message: TgMessage) -> None:
    """Create the user row and ping the owner with approve/deny buttons."""
    tg_user = message.from_user
    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(
            tg_user.id, telegram_chat_id=message.chat.id,
            username=tg_user.username, first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            language_code=tg_user.language_code,
        )
        already_requested = bool(user.settings.get("access_requested"))
        if not already_requested:
            user.settings = {**user.settings, "access_requested": True}
    await message.answer(
        "Привет! Я Lumi — личный ассистент.\n"
        "Доступ выдается по приглашению. Заявка отправлена владельцу — "
        "напишу, как только тебя подтвердят."
    )
    if already_requested:
        return
    settings = get_settings()
    if not settings.allowed_telegram_user_ids:
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    name = " ".join(filter(None, [tg_user.first_name, tg_user.last_name])) or "—"
    handle = f"@{tg_user.username}" if tg_user.username else f"id {tg_user.id}"
    owner = type("U", (), {"telegram_chat_id": settings.allowed_telegram_user_ids[0],
                           "telegram_user_id": settings.allowed_telegram_user_ids[0]})()
    from lumi.services.notifier import send_telegram_message

    await send_telegram_message(
        owner,  # type: ignore[arg-type]
        f"🔑 Заявка на доступ к Lumi:\n{name} ({handle})",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✓ Принять", callback_data=f"access_grant:{tg_user.id}"),
            InlineKeyboardButton(text="✗ Отклонить", callback_data=f"access_deny:{tg_user.id}"),
        ]]),
    )


async def _reply_chunks(message: TgMessage, text: str, reply_markup=None) -> None:
    text = telegram_plain_text(text)
    chunks = chunk_telegram(text)
    for i, chunk in enumerate(chunks):
        await message.answer(chunk, reply_markup=reply_markup if i == len(chunks) - 1 else None)


async def _record_rejected_attachment_turn(
    message: TgMessage,
    *,
    text: str,
    supported_images: list[dict],
    unsupported_attachments: list[dict],
    rejection_reason: str,
    telegram_message_ids: list[int],
    media_group_id: str | None,
    telegram_message_id: int,
    reply_text: str,
) -> None:
    if message.from_user is None:
        return
    stored_text = text.strip() or "[rejected attachments]"
    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(
            message.from_user.id,
            telegram_chat_id=message.chat.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=message.from_user.language_code,
        )
        conversation = await users.ensure_main_conversation(user)
        attachment_rejection = {
            "reason": rejection_reason,
            "telegram_message_ids": telegram_message_ids,
        }
        if media_group_id:
            attachment_rejection["media_group_id"] = media_group_id
        content_json = {
            "text": text,
            "attachment_rejection": attachment_rejection,
            "rejected_supported_images": supported_images,
            "unsupported_attachments": unsupported_attachments,
            "telegram_message_ids": telegram_message_ids,
            "media_group_id": media_group_id,
        }
        metadata = {
            "attachment_rejection": attachment_rejection,
            "rejected_supported_images": supported_images,
            "unsupported_attachments": unsupported_attachments,
            "telegram_message_ids": telegram_message_ids,
            "media_group_id": media_group_id,
        }
        session.add(Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.USER,
            content=stored_text,
            content_json=content_json,
            char_count=len(stored_text),
            telegram_message_id=telegram_message_id,
            telegram_chat_id=message.chat.id,
            metadata_={key: value for key, value in metadata.items() if value is not None},
        ))
        session.add(Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.ASSISTANT,
            content=reply_text,
            char_count=len(reply_text),
            telegram_chat_id=message.chat.id,
        ))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: TgMessage) -> None:
    if not await _check_allowed(message):
        await _request_access(message)
        return
    tg_user = message.from_user
    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(
            tg_user.id,
            telegram_chat_id=message.chat.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            language_code=tg_user.language_code,
        )
        await users.ensure_main_conversation(user)
        name = user.first_name or "привет"
    settings = get_settings()
    text = (
        f"Привет, {name}! Я Lumi — твой личный ассистент.\n\n"
        "Я веду задачи, напоминания, календарь, почту и новости — всё в одном чате.\n\n"
        "Попробуй написать:\n"
        "«Напомни завтра в 10 написать Саше по договору»\n\n"
        "Или открой Mini App — там Today, задачи, календарь и автоматизации.\n\n"
        "Хочешь, чтобы я сразу понимал твой контекст? Жми /intro — 5 коротких вопросов."
    )
    if not settings.mini_app_url:
        text += (
            "\n\nMini App URL еще не настроен. Укажи APP_PUBLIC_URL в .env "
            "после запуска HTTPS tunnel (например, cloudflared)."
        )
    await message.answer(text, reply_markup=start_keyboard())


@router.message(Command("intro"))
async def cmd_intro(message: TgMessage) -> None:
    if not await _check_allowed(message):
        return
    from lumi.bot.intro import INTRO_START_TEXT, set_intro_step

    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(
            message.from_user.id,
            telegram_chat_id=message.chat.id,
            language_code=_language_code(message),
        )
        set_intro_step(user, 0)
    await message.answer(INTRO_START_TEXT)


@router.message(Command("cancel"))
async def cmd_cancel(message: TgMessage) -> None:
    if not await _check_allowed(message):
        return
    from lumi.bot.intro import intro_step, set_intro_step

    async with session_scope() as session:
        user = await UserService(session).ensure_user(
            message.from_user.id,
            language_code=_language_code(message),
        )
        if intro_step(user) is not None:
            set_intro_step(user, None)
            await message.answer("Ок, прервал знакомство. Вернуться можно командой /intro.")
            return
    await message.answer("Нечего отменять.")


@router.message(Command("help"))
async def cmd_help(message: TgMessage) -> None:
    if not await _check_allowed(message):
        return
    await message.answer(HELP_TEXT)


@router.message(Command("app"))
async def cmd_app(message: TgMessage) -> None:
    if not await _check_allowed(message):
        return
    btn = mini_app_button()
    if btn is None:
        await message.answer(
            "Mini App URL еще не настроен. Запусти HTTPS tunnel "
            "(cloudflared tunnel --url http://localhost:8000) и пропиши APP_PUBLIC_URL в .env."
        )
        return
    from aiogram.types import InlineKeyboardMarkup

    await message.answer(
        "Открывай — всё в одном месте:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn]]),
    )


@router.message(Command("today"))
async def cmd_today(message: TgMessage) -> None:
    if not await _check_allowed(message):
        return
    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(
            message.from_user.id,
            telegram_chat_id=message.chat.id,
            language_code=_language_code(message),
        )
        payload = await TodayService(session).build_payload(user)
        text = format_today(payload, user.timezone)
        today_schedule = render_today_schedule(
            payload,
            timezone=user.timezone,
            language=_reply_language_for_message(user, _language_code(message)),
        )
    if today_schedule is not None:
        from lumi.services.notifier import send_telegram_message

        await send_telegram_message(
            user,
            today_schedule.plain_text,
            rich_html=today_schedule.rich_html,
            open_app_button=True,
        )
        return
    await _reply_chunks(message, text)


@router.message(Command("tasks"))
async def cmd_tasks(message: TgMessage) -> None:
    if not await _check_allowed(message):
        return
    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(
            message.from_user.id,
            telegram_chat_id=message.chat.id,
            language_code=_language_code(message),
        )
        tasks = await TaskService(session).list_active(user, limit=25)
        text = format_tasks(tasks, user.timezone)
    await _reply_chunks(message, text)


async def _enqueue_automation_run(message: TgMessage, automation_type: str, started_text: str) -> None:
    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(
            message.from_user.id,
            telegram_chat_id=message.chat.id,
            language_code=_language_code(message),
        )
        run = await RunService(session).create(
            user_id=user.id,
            type_=AGENT_RUN_TYPE_BY_AUTOMATION[automation_type],
            trigger="telegram_command",
        )
        run.metadata_ = {
            **(run.metadata_ or {}),
            "reply_language": _reply_language_for_message(user, _language_code(message)),
        }
        user_id = str(user.id)
        run_id = str(run.id)
    job_id = await enqueue_job(
        JOB_BY_AUTOMATION_TYPE[automation_type], user_id,
        agent_run_id=run_id, trigger="telegram_command",
    )
    if job_id:
        await message.answer(started_text)
    else:
        await message.answer("Очередь задач недоступна — проверь, что worker и Redis запущены.")


@router.message(Command("plan"))
async def cmd_plan(message: TgMessage) -> None:
    if not await _check_allowed(message):
        return
    await _enqueue_automation_run(message, "daily_planning", "Собираю план дня — пришлю через минуту.")


@router.message(Command("news"))
async def cmd_news(message: TgMessage) -> None:
    if not await _check_allowed(message):
        return
    await _enqueue_automation_run(message, "news_digest", "Собираю свежий дайджест — пришлю через пару минут.")


@router.message(Command("email"))
async def cmd_email(message: TgMessage) -> None:
    if not await _check_allowed(message):
        return
    await _enqueue_automation_run(message, "email_triage", "Разбираю почту — скоро пришлю выжимку.")


@router.message(Command("settings"))
async def cmd_settings(message: TgMessage) -> None:
    if not await _check_allowed(message):
        return
    settings = get_settings()
    from lumi.connectors.google.auth import connection_status

    google = await connection_status()
    async with session_scope() as session:
        user = await UserService(session).ensure_user(
            message.from_user.id,
            telegram_chat_id=message.chat.id,
            language_code=_language_code(message),
        )
        tz = user.timezone
    lines = [
        "Настройки Lumi:",
        f"• Часовой пояс: {tz}",
        f"• Модель: {settings.minimax_model if settings.llm_provider == 'minimax' else 'mock (тестовый режим)'}",
        f"• Google: {'подключен' if google['status'] == 'connected' else 'не подключен'}",
        f"• Mini App: {settings.mini_app_url or 'не настроен (нужен APP_PUBLIC_URL)'}",
        "",
        "Подробнее и управление — в Mini App, раздел Settings.",
    ]
    await message.answer("\n".join(lines))


# ---------------------------------------------------------------------------
# Chat message -> orchestrator
# ---------------------------------------------------------------------------

@router.message((F.text & ~F.text.startswith("/")) | F.photo | F.document | F.video)
async def on_chat_message(message: TgMessage, bot: Bot, telegram_update_id: int | None = None) -> None:
    if not await _check_allowed(message):
        return
    telegram_update_id_var.set(telegram_update_id or message.message_id)
    batch_item = classify_attachment_message(message)
    if batch_item.media_group_id:
        try:
            redis = await get_queue()
            logical_message = await AttachmentBatchBuffer(redis).add_and_maybe_finalize(batch_item)
        except Exception:  # noqa: BLE001
            log.exception("telegram attachment batch buffering failed")
            logical_message = build_logical_message([batch_item])
        if logical_message is None:
            return
    else:
        logical_message = build_logical_message([batch_item])

    text = logical_message.text
    image_ref = logical_message.image_ref
    supported_images = [image.to_metadata() for image in (logical_message.supported_images or [])]
    unsupported_attachments = list(logical_message.unsupported_attachments or [])

    if logical_message.is_rejected:
        await _record_rejected_attachment_turn(
            message,
            text=text,
            supported_images=supported_images,
            unsupported_attachments=unsupported_attachments,
            rejection_reason=logical_message.rejection_reason or "attachment_rejected",
            telegram_message_ids=list(logical_message.telegram_message_ids or [message.message_id]),
            media_group_id=logical_message.media_group_id,
            telegram_message_id=logical_message.primary_message_id,
            reply_text=REJECTED_ATTACHMENT_REPLY,
        )
        await message.answer(REJECTED_ATTACHMENT_REPLY)
        return

    # Onboarding interview intercepts plain text until finished.
    from lumi.bot.intro import handle_intro_answer, intro_step

    async with session_scope() as session:
        user = await UserService(session).ensure_user(
            message.from_user.id,
            telegram_chat_id=message.chat.id,
            language_code=_language_code(message),
        )
        if intro_step(user) is not None:
            if not text:
                await message.answer("Сейчас идет /intro — ответь текстом или нажми /cancel.")
                return
            reply, _finished = await handle_intro_answer(session, user, text)
            await commit_with_realtime(session)
            await message.answer(reply)
            return
        if image_ref is None and not logical_message.media_group_id and message.reply_to_message:
            image_ref = extract_image_ref(message.reply_to_message, source="reply")

    if image_ref is not None:
        if image_ref.file_size and image_ref.file_size > get_settings().telegram_image_max_bytes:
            await message.answer("Картинка слишком большая. Пришли изображение до 10 MB.")
            return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        async with session_scope() as session:
            result = await TelegramIntakeService(session).ingest_chat_message(
                update_id=telegram_update_id,
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
                telegram_message_id=logical_message.primary_message_id,
                text=text,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                language_code=message.from_user.language_code,
                image_metadata=image_ref.to_metadata() if image_ref else None,
                ignored_attachments=[],
                payload={
                    "media_group_id": logical_message.media_group_id,
                    "telegram_message_ids": list(
                        logical_message.telegram_message_ids or [logical_message.primary_message_id]
                    ),
                },
            )
    except Exception:  # noqa: BLE001 — the bot must always answer
        log.exception("telegram turn intake failed")
        await message.answer("Не смог поставить сообщение в очередь. Попробуй еще раз.")
        return
    if result.duplicate_update:
        return
    if result.turn is None:
        await message.answer("Очередь сообщений переполнена. Дождись текущего ответа и повтори.")
        return

    if result.created_turn:
        try:
            status_msg = await message.answer("⏳")
        except Exception:  # noqa: BLE001
            status_msg = None
        status_message_id = getattr(status_msg, "message_id", None)
        if status_message_id is not None:
            async with session_scope() as session:
                await TurnService(session).set_status_message(result.turn.id, status_message_id)

    enqueue_kwargs = {}
    if result.enqueue_at is not None:
        enqueue_kwargs["_defer_until"] = result.enqueue_at
        enqueue_kwargs["_job_id"] = _deadline_job_id(result.turn.id, result.enqueue_at)
    job_id = await enqueue_job("process_assistant_turn", str(result.turn.id), **enqueue_kwargs)
    if not job_id:
        log.info(
            "assistant turn enqueue skipped or duplicated",
            fields={"turn_id": str(result.turn.id)},
        )


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("confirm:") | F.data.startswith("reject:"))
async def on_confirmation(callback: CallbackQuery) -> None:
    if not await _check_allowed(callback):
        await callback.answer()
        return
    action, _, confirmation_id_raw = callback.data.partition(":")
    accept = action == "confirm"
    try:
        confirmation_id = uuid.UUID(confirmation_id_raw)
    except ValueError:
        await callback.answer("Неизвестное действие")
        return

    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(callback.from_user.id)
        confirmations = ConfirmationService(session)
        confirmation = await confirmations.get(user, confirmation_id)
        if confirmation is None:
            await callback.answer("Уже неактуально")
            return
        if confirmation.status != ConfirmationStatus.PENDING:
            await callback.answer("Уже решено")
            return
        confirmation = await confirmations.decide(user, confirmation, accept=accept)
        if accept and confirmation.status == ConfirmationStatus.ACCEPTED:
            text = await ConfirmationExecutor(session).execute(user, confirmation)
        elif confirmation.status == ConfirmationStatus.EXPIRED:
            text = "Это предложение уже истекло."
        else:
            text = "Ок, не делаю."
    await callback.answer("Готово" if accept else "Отменено")
    if callback.message:
        await callback.message.answer(text)


@router.callback_query(F.data.startswith("rename_pick:"))
async def on_rename_pick(callback: CallbackQuery) -> None:
    if not await _check_allowed(callback):
        await callback.answer()
        return
    _, _, rest = (callback.data or "").partition(":")
    token, _, index_raw = rest.partition(":")
    try:
        index = int(index_raw)
    except ValueError:
        await callback.answer("Неизвестное действие")
        return

    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(callback.from_user.id)
        confirmations = ConfirmationService(session)
        pending = await confirmations.list_pending(user, limit=100)
        matches = [
            confirmation for confirmation in pending
            if confirmation.action_type == "rename_task_choice"
            and confirmation.id.hex.startswith(token)
        ]
        if len(matches) != 1:
            await callback.answer("Уже неактуально")
            return
        confirmation = matches[0]
        payload = confirmation.action_payload
        candidate_ids = list(payload.get("candidate_task_ids") or [])
        new_title = str(payload.get("new_title") or "").strip()
        if index < 0 or index >= len(candidate_ids) or not new_title:
            await callback.answer("Неизвестное действие")
            return
        try:
            task_id = uuid.UUID(candidate_ids[index])
        except ValueError:
            await callback.answer("Неизвестное действие")
            return
        agent_run_id = None
        if payload.get("agent_run_id"):
            try:
                agent_run_id = uuid.UUID(str(payload["agent_run_id"]))
            except ValueError:
                agent_run_id = None

        result = await TaskService(session).rename_open_task_by_id(
            user,
            task_id,
            new_title=new_title,
            actor="user",
            agent_run_id=agent_run_id,
        )
        await confirmations.decide(user, confirmation, accept=True)
        if agent_run_id:
            run = await RunService(session).get(agent_run_id, user.id)
            if run is not None:
                await RunService(session).log_tool_call(
                    run=run,
                    tool_name="rename_task",
                    status="completed" if result.status == "renamed" else "skipped",
                    args=payload,
                    result={
                        "status": result.status,
                        "task_id": str(result.task.id) if result.task else str(task_id),
                    },
                )
        if result.status == "renamed":
            text = f"Готово: переименовал «{result.old_title}» → «{result.new_title}»."
        else:
            text = "Эта задача уже закрыта или удалена — переименовывать нечего."

    await callback.answer("Готово" if result.status == "renamed" else "Неактуально")
    if callback.message:
        await callback.message.answer(text)


@router.callback_query(F.data.startswith("update_pick:"))
async def on_update_pick(callback: CallbackQuery) -> None:
    if not await _check_allowed(callback):
        await callback.answer()
        return
    _, _, rest = (callback.data or "").partition(":")
    token, _, index_raw = rest.partition(":")
    try:
        index = int(index_raw)
    except ValueError:
        await callback.answer("Неизвестное действие")
        return

    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(callback.from_user.id)
        confirmations = ConfirmationService(session)
        pending = await confirmations.list_pending(user, limit=100)
        matches = [
            confirmation for confirmation in pending
            if confirmation.action_type == "update_task_choice"
            and confirmation.id.hex.startswith(token)
        ]
        if len(matches) != 1:
            await callback.answer("Уже неактуально")
            return
        confirmation = matches[0]
        payload = confirmation.action_payload
        candidate_ids = list(payload.get("candidate_task_ids") or [])
        updates = payload.get("updates")
        if index < 0 or index >= len(candidate_ids) or not isinstance(updates, dict) or not updates:
            await callback.answer("Неизвестное действие")
            return
        try:
            task_id = uuid.UUID(candidate_ids[index])
        except ValueError:
            await callback.answer("Неизвестное действие")
            return
        agent_run_id = None
        if payload.get("agent_run_id"):
            try:
                agent_run_id = uuid.UUID(str(payload["agent_run_id"]))
            except ValueError:
                agent_run_id = None

        tasks = TaskService(session)
        task = await tasks.get(user, task_id)
        if task is None:
            await callback.answer("Задача не найдена")
            return
        task = await tasks.update_task(
            user,
            task,
            updates,
            actor="user",
            agent_run_id=agent_run_id,
        )
        await confirmations.decide(user, confirmation, accept=True)
        if agent_run_id:
            run = await RunService(session).get(agent_run_id, user.id)
            if run is not None:
                await RunService(session).log_tool_call(
                    run=run,
                    tool_name="update_task",
                    status="completed",
                    args=payload,
                    result={"task_id": str(task.id), "updated_fields": sorted(updates)},
                )
        text = format_task_update_reply(
            task,
            updates,
            language=str(payload.get("language") or ""),
        )

    await callback.answer("Готово")
    if callback.message:
        await callback.message.answer(text)


@router.callback_query(F.data.startswith("task_done:"))
async def on_task_done(callback: CallbackQuery) -> None:
    if not await _check_allowed(callback):
        await callback.answer()
        return
    task_id_raw = callback.data.split(":", 1)[1]
    async with session_scope() as session:
        user = await UserService(session).ensure_user(callback.from_user.id)
        tasks = TaskService(session)
        try:
            task = await tasks.get(user, uuid.UUID(task_id_raw))
        except ValueError:
            task = None
        if task is None:
            await callback.answer("Задача не найдена")
            return
        await tasks.complete_task(user, task)
        title = task.title
    await callback.answer("Отмечено выполненным ✓")
    if callback.message:
        await callback.message.answer(f"✓ Готово: {title}")


@router.callback_query(F.data.startswith("task_snooze:"))
async def on_task_snooze(callback: CallbackQuery) -> None:
    if not await _check_allowed(callback):
        await callback.answer()
        return
    parts = callback.data.split(":")
    task_id_raw = parts[1] if len(parts) > 1 else ""
    preset = parts[2] if len(parts) > 2 else "1h"
    async with session_scope() as session:
        user = await UserService(session).ensure_user(callback.from_user.id)
        tasks = TaskService(session)
        try:
            task = await tasks.get(user, uuid.UUID(task_id_raw))
        except ValueError:
            task = None
        if task is None:
            await callback.answer("Задача не найдена")
            return
        task = await tasks.snooze_task(user, task, preset=preset)
        from lumi.utils.time import fmt_local

        when = fmt_local(task.snoozed_until, user.timezone)
    await callback.answer(f"Отложено до {when}")


@router.callback_query(F.data.startswith("snooze_pick:"))
async def on_snooze_pick(callback: CallbackQuery) -> None:
    if not await _check_allowed(callback):
        await callback.answer()
        return
    _, _, rest = (callback.data or "").partition(":")
    token, _, index_raw = rest.partition(":")
    try:
        index = int(index_raw)
    except ValueError:
        await callback.answer("Неизвестное действие")
        return

    async with session_scope() as session:
        user = await UserService(session).ensure_user(callback.from_user.id)
        confirmations = ConfirmationService(session)
        pending = await confirmations.list_pending(user, limit=100)
        matches = [
            confirmation for confirmation in pending
            if confirmation.action_type == "snooze_task_choice"
            and confirmation.id.hex.startswith(token)
        ]
        if len(matches) != 1:
            await callback.answer("Уже неактуально")
            return
        confirmation = matches[0]
        payload = confirmation.action_payload
        candidate_ids = list(payload.get("candidate_task_ids") or [])
        preset = str(payload.get("preset") or "tomorrow")
        if index < 0 or index >= len(candidate_ids):
            await callback.answer("Неизвестное действие")
            return
        try:
            task_id = uuid.UUID(candidate_ids[index])
        except ValueError:
            await callback.answer("Неизвестное действие")
            return
        agent_run_id = None
        if payload.get("agent_run_id"):
            try:
                agent_run_id = uuid.UUID(str(payload["agent_run_id"]))
            except ValueError:
                agent_run_id = None

        tasks = TaskService(session)
        task = await tasks.get(user, task_id)
        if task is None:
            await callback.answer("Задача не найдена")
            return
        task = await tasks.snooze_task(user, task, preset=preset, actor="user")
        await confirmations.decide(user, confirmation, accept=True)
        if agent_run_id:
            run = await RunService(session).get(agent_run_id, user.id)
            if run is not None:
                await RunService(session).log_tool_call(
                    run=run,
                    tool_name="snooze_task",
                    status="completed",
                    args=payload,
                    result={
                        "task_id": str(task.id),
                        "snoozed_until": task.snoozed_until.isoformat()
                        if task.snoozed_until else None,
                    },
                )
        from lumi.utils.time import fmt_local

        when = fmt_local(task.snoozed_until, user.timezone)
        text = f"Готово: отложил «{task.title}» до {when}."

    await callback.answer(f"Отложено до {when}")
    if callback.message:
        await callback.message.answer(text)


@router.callback_query(F.data.startswith("block_confirm:"))
async def on_block_confirm(callback: CallbackQuery) -> None:
    if not await _check_allowed(callback):
        await callback.answer()
        return
    block_id_raw = callback.data.split(":", 1)[1]
    async with session_scope() as session:
        user = await UserService(session).ensure_user(callback.from_user.id)
        from lumi.services.calendar import CalendarService

        calendar = CalendarService(session)
        try:
            event = await calendar.get_event(user, uuid.UUID(block_id_raw))
        except ValueError:
            event = None
        language = _reply_language_for_callback(user, _language_code(callback))
        if event is not None:
            language = normalize_reply_language(
                str((event.metadata_ or {}).get("reply_language") or language)
            )
        if event is None or event.status != CalendarEventStatus.PROPOSED:
            await callback.answer(_block_confirm_missing_text(language))
            return
        await calendar.confirm_proposed_block(user, event)
        from lumi.utils.time import fmt_local

        text = _block_confirmed_text(
            language,
            title=event.title,
            start_label=fmt_local(event.start_at, user.timezone, "%d.%m %H:%M"),
            end_label=fmt_local(event.end_at, user.timezone, "%H:%M"),
        )
    await callback.answer(_block_confirm_accepted_text(language))
    if callback.message:
        await callback.message.answer(text)


@router.callback_query(F.data == "email_create_tasks")
async def on_email_create_tasks(callback: CallbackQuery) -> None:
    if not await _check_allowed(callback):
        await callback.answer()
        return
    async with session_scope() as session:
        user = await UserService(session).ensure_user(callback.from_user.id)
        from sqlalchemy import select

        from lumi.db.models import EmailThread
        from lumi.utils.time import local_to_utc

        result = await session.execute(
            select(EmailThread).where(
                EmailThread.user_id == user.id,
                EmailThread.triage_status == "triaged",
            ).order_by(EmailThread.updated_at.desc()).limit(20)
        )
        tasks_service = TaskService(session)
        created: list[str] = []
        for thread in result.scalars():
            candidate = thread.metadata_.get("task_candidate")
            if not candidate or thread.metadata_.get("task_created"):
                continue
            due_at = None
            if candidate.get("due_at_local"):
                from datetime import datetime

                try:
                    due_at = local_to_utc(
                        datetime.fromisoformat(candidate["due_at_local"]), user.timezone
                    )
                except ValueError:
                    due_at = None
            task = await tasks_service.create_task(
                user,
                title=candidate.get("title") or (thread.subject or "Письмо"),
                priority=candidate.get("priority", "medium"),
                due_at=due_at,
                source="email",
                created_by="agent",
                actor="user",
            )
            thread.metadata_ = {**thread.metadata_, "task_created": str(task.id)}
            created.append(task.title)
    await callback.answer(f"Создано задач: {len(created)}")
    if callback.message and created:
        await callback.message.answer(
            "Создал задачи из почты:\n" + "\n".join(f"• {t}" for t in created)
        )
    elif callback.message:
        await callback.message.answer("Новых задач из почты не нашлось — всё уже создано.")


@router.callback_query(F.data.startswith("access_grant:") | F.data.startswith("access_deny:"))
async def on_access_decision(callback: CallbackQuery) -> None:
    if callback.from_user is None or not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    action, _, raw_id = callback.data.partition(":")
    try:
        target_id = int(raw_id)
    except ValueError:
        await callback.answer("Ошибка")
        return
    grant = action == "access_grant"
    async with session_scope() as session:
        users = UserService(session)
        target = await users.ensure_user(target_id)
        target.is_allowed = grant
        target_ref = target
        from lumi.services.audit import AuditService

        await AuditService(session).log(
            user_id=target.id, actor="user", entity_type="user",
            action="access_granted" if grant else "access_denied", details={},
        )
    await callback.answer("Принят" if grant else "Отклонен")
    if callback.message:
        await callback.message.edit_text(
            (callback.message.text or "") + ("\n\n✓ Доступ выдан" if grant else "\n\n✗ Отклонено")
        )
    from lumi.services.notifier import send_telegram_message

    if grant:
        await send_telegram_message(
            target_ref,
            "Доступ открыт — добро пожаловать в Lumi! 🎉\n"
            "Начни с /intro (короткое знакомство) или сразу пиши, что нужно сделать.",
        )


@router.callback_query(F.data.startswith("run:"))
async def on_run_automation(callback: CallbackQuery) -> None:
    if not await _check_allowed(callback):
        await callback.answer()
        return
    automation_type = callback.data.split(":", 1)[1]
    if automation_type not in JOB_BY_AUTOMATION_TYPE:
        await callback.answer("Неизвестный тип")
        return
    async with session_scope() as session:
        user = await UserService(session).ensure_user(callback.from_user.id)
        run = await RunService(session).create(
            user_id=user.id,
            type_=AGENT_RUN_TYPE_BY_AUTOMATION[automation_type],
            trigger="telegram_callback",
        )
        user_id, run_id = str(user.id), str(run.id)
    job_id = await enqueue_job(
        JOB_BY_AUTOMATION_TYPE[automation_type], user_id,
        agent_run_id=run_id, trigger="telegram_callback",
    )
    await callback.answer("Запустил" if job_id else "Очередь недоступна")
    if callback.message and job_id:
        names = {
            "news_digest": "Собираю дайджест…",
            "email_triage": "Разбираю почту…",
            "daily_planning": "Собираю план дня…",
            "calendar_sync": "Синхронизирую календарь…",
        }
        await callback.message.answer(names.get(automation_type, "Запустил…"))
