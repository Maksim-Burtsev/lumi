"""arq worker jobs: task planning, calendar sync, reminders, and chat maintenance."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from time import monotonic
from typing import Any

import httpx
from sqlalchemy import select

from lumi.assistant.orchestrator import AssistantOrchestrator
from lumi.bot.formatting import rich_html_requires_rich_message, telegram_plain_text
from lumi.bot.keyboards import markup_from_buttons
from lumi.bot.schedule_messages import (
    ScheduleMessageItem,
    render_schedule_message,
    schedule_plan_title,
)
from lumi.config import get_settings
from lumi.db.models import (
    AgentRun,
    AgentRunType,
    AssistantOpportunityJob,
    AssistantTurn,
    Conversation,
    Message,
    MessageRole,
    ScheduledTask,
    Task,
    TaskStatus,
    User,
)
from lumi.db.session import session_scope
from lumi.i18n import normalize_app_locale, normalize_reply_language
from lumi.llm.base import LLMError, LLMMessage
from lumi.llm.gateway import LLMGateway
from lumi.logging import agent_run_id_var, get_logger
from lumi.services.assistant_suggestions import AssistantSuggestionService
from lumi.services.calendar import CalendarService
from lumi.services.planning_settings import normalize_planning_settings
from lumi.services.runs import RunService
from lumi.services.turns import TurnService
from lumi.services.users import UserService
from lumi.utils.text import chunk_telegram, ru_plural
from lumi.utils.time import fmt_local, get_zone, utc_now
from lumi.worker.queue import enqueue_job

log = get_logger(__name__)


def _deadline_job_id(turn_id: str | uuid.UUID, deadline) -> str:
    return f"assistant-turn:{turn_id}:at:{int(deadline.timestamp() * 1000)}"


async def _load_user(session, user_id: str) -> User | None:
    result = await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
    return result.scalar_one_or_none()


async def _load_turn_user(session, turn: AssistantTurn) -> User | None:
    result = await session.execute(select(User).where(User.id == turn.user_id))
    return result.scalar_one_or_none()


def _telegram_json(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    return value


async def _telegram_api_post(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    timeout = httpx.Timeout(connect=5, read=20, write=10, pool=5)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload,
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Telegram {method} returned non-JSON response") from exc
    if response.status_code >= 400 or data.get("ok") is not True:
        description = data.get("description") or response.text[:200]
        raise RuntimeError(f"Telegram {method} failed: {description}")
    return data


def _rich_message_payload(html: str) -> dict[str, Any]:
    return {"html": html, "skip_entity_detection": True}


def _without_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _telegram_message_not_modified(exc: Exception) -> bool:
    return "message is not modified" in str(exc).lower()


def _float_setting(settings, name: str, default: float) -> float:
    try:
        return float(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def _progress_heartbeat_text(settings, *, elapsed_seconds: float, tick: int, last_progress_text: str | None) -> str:
    stale_after = _float_setting(settings, "telegram_progress_stale_after_seconds", 12.0)
    long_after = _float_setting(settings, "telegram_progress_long_after_seconds", 30.0)
    if elapsed_seconds >= long_after:
        base = "Still working, this is taking longer than usual"
    elif elapsed_seconds >= stale_after:
        base = "Still thinking"
    else:
        base = (last_progress_text or "Thinking").strip().rstrip(".") or "Thinking"
    dots = "." * ((tick % 3) + 1)
    return f"{base}{dots}"


def _user_visible_progress_text(status_text: str) -> str:
    raw_text = str(status_text or "").strip()
    if raw_text == "__thinking__":
        return "Thinking..."
    return telegram_plain_text(raw_text).strip()


def _run_reply_language(run: AgentRun, user: User) -> str:
    metadata = run.metadata_ or {}
    return normalize_reply_language(str(metadata.get("reply_language") or user.locale))


async def send_turn_reply(
    *,
    user: User,
    turn: AssistantTurn,
    reply_text: str,
    buttons,
    reply_rich_html: str | None = None,
    open_app_button: bool = False,
    open_app_button_label: str | None = None,
) -> bool:
    settings = get_settings()
    if not settings.telegram_bot_token:
        log.warning("cannot send turn reply: TELEGRAM_BOT_TOKEN is not set")
        return False
    from aiogram import Bot
    from aiogram.types import LinkPreviewOptions

    bot = Bot(token=settings.telegram_bot_token)
    chat_id = turn.telegram_chat_id or user.telegram_chat_id or user.telegram_user_id
    chunks = chunk_telegram(telegram_plain_text(reply_text))
    markup = markup_from_buttons(
        buttons,
        with_app_button=open_app_button,
        app_button_text=open_app_button_label,
    )
    markup_payload = _telegram_json(markup)
    link_preview_options = LinkPreviewOptions(is_disabled=True)
    rich_html = reply_rich_html if reply_rich_html and len(chunks) == 1 else None
    use_bot_api_rich = bool(getattr(settings, "telegram_use_rich_messages", False))
    try:
        if turn.status_message_id and len(chunks) == 1:
            try:
                if rich_html and use_bot_api_rich:
                    await _telegram_api_post(
                        settings.telegram_bot_token,
                        "editMessageText",
                        _without_none({
                            "chat_id": chat_id,
                            "message_id": turn.status_message_id,
                            "rich_message": _rich_message_payload(rich_html),
                            "reply_markup": markup_payload,
                        }),
                    )
                    return True
                if rich_html:
                    if rich_html_requires_rich_message(rich_html):
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=turn.status_message_id,
                            text=chunks[0],
                            link_preview_options=link_preview_options,
                            reply_markup=markup,
                        )
                    else:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=turn.status_message_id,
                            text=rich_html,
                            link_preview_options=link_preview_options,
                            reply_markup=markup,
                            parse_mode="HTML",
                        )
                    return True
                else:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=turn.status_message_id,
                        text=chunks[0],
                        link_preview_options=link_preview_options,
                        reply_markup=markup,
                    )
                    return True
            except Exception as exc:  # noqa: BLE001 — status edit can fail after restarts/deletes
                if _telegram_message_not_modified(exc):
                    return True
                log.exception("telegram status edit failed; falling back to send_message")
        if rich_html:
            if use_bot_api_rich:
                try:
                    await _telegram_api_post(
                        settings.telegram_bot_token,
                        "sendRichMessage",
                        _without_none({
                            "chat_id": chat_id,
                            "rich_message": _rich_message_payload(rich_html),
                            "reply_markup": markup_payload,
                        }),
                    )
                    if turn.status_message_id:
                        try:
                            await bot.delete_message(chat_id=chat_id, message_id=turn.status_message_id)
                        except Exception:  # noqa: BLE001
                            log.info("telegram status delete skipped after rich send")
                    return True
                except Exception:  # noqa: BLE001 — rich messages are new; plain fallback must work
                    log.exception("telegram rich turn reply failed; falling back to send_message")
            if rich_html_requires_rich_message(rich_html):
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunks[0],
                    link_preview_options=link_preview_options,
                    reply_markup=markup,
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=rich_html,
                    link_preview_options=link_preview_options,
                    reply_markup=markup,
                    parse_mode="HTML",
                )
            if turn.status_message_id:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=turn.status_message_id)
                except Exception:  # noqa: BLE001
                    log.info("telegram status delete skipped after html fallback")
            return True
        start_index = 0
        if turn.status_message_id and chunks:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=turn.status_message_id,
                    text=chunks[0],
                    link_preview_options=link_preview_options,
                    reply_markup=markup if len(chunks) == 1 else None,
                )
                start_index = 1
                if len(chunks) == 1:
                    return True
            except Exception as exc:  # noqa: BLE001 — final delivery must still fall back to fresh messages
                if _telegram_message_not_modified(exc):
                    start_index = 1
                    if len(chunks) == 1:
                        return True
                else:
                    log.exception("telegram status edit failed; falling back to send_message")
        for i, chunk in enumerate(chunks[start_index:], start=start_index):
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                link_preview_options=link_preview_options,
                reply_markup=markup if i == len(chunks) - 1 else None,
            )
        return True
    except Exception:  # noqa: BLE001
        log.exception("telegram turn reply failed")
        return False
    finally:
        await bot.session.close()


async def edit_turn_status_message(
    *,
    user: User,
    turn: AssistantTurn,
    status_text: str,
) -> bool:
    settings = get_settings()
    if not settings.telegram_bot_token or not turn.status_message_id:
        return False
    from aiogram import Bot
    from aiogram.types import LinkPreviewOptions

    bot = Bot(token=settings.telegram_bot_token)
    chat_id = turn.telegram_chat_id or user.telegram_chat_id or user.telegram_user_id
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=turn.status_message_id,
            text=telegram_plain_text(status_text),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return True
    except Exception:  # noqa: BLE001 — progress edits are best-effort
        log.info("telegram progress status edit skipped")
        return False
    finally:
        await bot.session.close()


async def send_turn_chat_action(
    *,
    user: User,
    turn: AssistantTurn,
    action: str = "typing",
) -> bool:
    settings = get_settings()
    if not settings.telegram_bot_token:
        return False
    from aiogram import Bot

    bot = Bot(token=settings.telegram_bot_token)
    chat_id = turn.telegram_chat_id or user.telegram_chat_id or user.telegram_user_id
    try:
        await bot.send_chat_action(chat_id=chat_id, action=action)
        return True
    except Exception:  # noqa: BLE001 — chat actions are best-effort
        log.info("telegram chat action skipped")
        return False
    finally:
        await bot.session.close()


async def _run_turn_progress_heartbeat(
    *,
    settings,
    user: User,
    turn: AssistantTurn,
    started_at: float,
    stream_started,
    current_progress_text,
    edit_progress_status,
) -> None:
    status_interval = max(0.01, _float_setting(settings, "telegram_progress_heartbeat_interval_seconds", 3.0))
    chat_action_interval = max(0.01, _float_setting(settings, "telegram_chat_action_interval_seconds", 4.0))
    next_status_at = monotonic() + status_interval
    next_chat_action_at = monotonic()
    tick = 0
    while True:
        now = monotonic()
        if now >= next_chat_action_at:
            await send_turn_chat_action(user=user, turn=turn, action="typing")
            next_chat_action_at = now + chat_action_interval
        if turn.status_message_id and not stream_started() and now >= next_status_at:
            status_text = _progress_heartbeat_text(
                settings,
                elapsed_seconds=now - started_at,
                tick=tick,
                last_progress_text=current_progress_text(),
            )
            await edit_progress_status(status_text)
            tick += 1
            next_status_at = now + status_interval
        await asyncio.sleep(min(0.5, status_interval, chat_action_interval))


async def _enqueue_turn(turn: AssistantTurn, *, delay_seconds: float | None = None) -> None:
    kwargs: dict[str, Any] = {}
    if delay_seconds is not None:
        kwargs["_defer_by"] = timedelta(seconds=delay_seconds)
    elif turn.debounce_deadline_at:
        kwargs["_defer_until"] = turn.debounce_deadline_at
        kwargs["_job_id"] = _deadline_job_id(turn.id, turn.debounce_deadline_at)
    await enqueue_job("process_assistant_turn", str(turn.id), **kwargs)


async def _enqueue_turn_id(
    turn_id: str,
    *,
    delay_seconds: float | None = None,
    defer_until=None,
) -> str | None:
    kwargs: dict[str, Any] = {}
    if delay_seconds is not None:
        kwargs["_defer_by"] = timedelta(seconds=delay_seconds)
    if defer_until is not None:
        kwargs["_defer_until"] = defer_until
        kwargs["_job_id"] = _deadline_job_id(turn_id, defer_until)
    return await enqueue_job("process_assistant_turn", turn_id, **kwargs)


def _delivery_retry_delay(settings, retry_count: int) -> int:
    base = max(1, settings.telegram_turn_retry_base_seconds)
    return min(base * (2 ** max(0, retry_count - 1)), 300)


async def _get_or_create_run(
    session, *, user: User, run_id: str | None, type_: AgentRunType, trigger: str,
    scheduled_task_id: str | None = None,
) -> AgentRun:
    runs = RunService(session)
    if run_id:
        run = await runs.get(uuid.UUID(run_id), user.id)
        if run:
            return run
    return await runs.create(
        user_id=user.id,
        type_=type_,
        trigger=trigger,
        scheduled_task_id=uuid.UUID(scheduled_task_id) if scheduled_task_id else None,
    )


async def _update_scheduled_task(session, scheduled_task_id: str | None, *, error: str | None) -> None:
    if not scheduled_task_id:
        return
    result = await session.execute(
        select(ScheduledTask).where(ScheduledTask.id == uuid.UUID(scheduled_task_id))
    )
    task = result.scalar_one_or_none()
    if task is None:
        return
    from lumi.services.automations import AutomationService

    service = AutomationService(session)
    if error:
        await service.mark_failed(task, error)
    else:
        await service.mark_succeeded(task)


def _job(type_: AgentRunType):
    """Decorator: run lifecycle, scheduled task bookkeeping, error isolation."""

    def wrap(fn):
        async def runner(
            ctx: dict[str, Any],
            user_id: str,
            *,
            agent_run_id: str | None = None,
            scheduled_task_id: str | None = None,
            trigger: str = "manual_api",
            notify: bool = True,
            **kwargs: Any,
        ) -> str:
            async with session_scope() as session:
                user = await _load_user(session, user_id)
                if user is None:
                    return "user not found"
                run = await _get_or_create_run(
                    session, user=user, run_id=agent_run_id, type_=type_,
                    trigger=trigger, scheduled_task_id=scheduled_task_id,
                )
                runs = RunService(session)
                await runs.mark_running(run)
                agent_run_id_var.set(str(run.id))
                try:
                    summary = await fn(
                        session=session, user=user, run=run, notify=notify, **kwargs
                    )
                    await runs.mark_completed(run, summary)
                    await _update_scheduled_task(session, scheduled_task_id, error=None)
                    return summary or "ok"
                except Exception as exc:  # noqa: BLE001 — job must record its own failure
                    log.exception("job failed", fields={"job": fn.__name__})
                    await runs.mark_failed(run, str(exc))
                    await _update_scheduled_task(session, scheduled_task_id, error=str(exc))
                    return f"failed: {exc}"

        # arq registers functions by __qualname__ — make the wrapper transparent.
        runner.__name__ = fn.__name__
        runner.__qualname__ = fn.__name__
        return runner

    return wrap


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

async def process_assistant_turn(ctx: dict[str, Any], turn_id: str) -> str:
    settings = get_settings()
    parsed_turn_id = uuid.UUID(turn_id)
    turn_snapshot: dict[str, Any]
    user_snapshot: dict[str, Any]

    async with session_scope() as session:
        turns = TurnService(session)
        acquired = await turns.acquire_turn(
            parsed_turn_id, lock_seconds=settings.telegram_turn_lock_seconds
        )
        if acquired.status == "deferred":
            if acquired.enqueue_at:
                await _enqueue_turn_id(turn_id, defer_until=acquired.enqueue_at)
            return "turn deferred"
        if acquired.status == "locked":
            await _enqueue_turn_id(turn_id, delay_seconds=3)
            return "turn locked"
        if acquired.status == "already_running":
            return "turn already running"
        if acquired.status == "not_ready":
            if acquired.turn is not None:
                await _enqueue_turn(acquired.turn)
            else:
                await _enqueue_turn_id(turn_id, delay_seconds=3)
            return "turn not ready"
        if acquired.status != "acquired" or acquired.turn is None:
            return f"turn {acquired.status}"

        turn = acquired.turn
        user = await _load_turn_user(session, turn)
        if user is None:
            await turns.fail_turn(turn.id, "user not found")
            return "user not found"

        turn_snapshot = {
            "id": turn.id,
            "conversation_id": turn.conversation_id,
            "telegram_chat_id": turn.telegram_chat_id,
            "primary_message_id": turn.primary_message_id,
            "input_text": turn.input_text,
            "payload": dict(turn.payload or {}),
            "status_message_id": turn.status_message_id,
            "retry_count": turn.retry_count,
            "created_at": turn.created_at,
            "started_at": turn.started_at,
        }
        user_snapshot = {
            "id": user.id,
            "telegram_user_id": user.telegram_user_id,
            "telegram_chat_id": user.telegram_chat_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }

    queue_wait_ms = None
    if turn_snapshot.get("created_at") is not None and turn_snapshot.get("started_at") is not None:
        queue_wait_ms = max(
            0,
            int((turn_snapshot["started_at"] - turn_snapshot["created_at"]).total_seconds() * 1000),
        )
    log.info(
        "assistant turn acquired",
        fields={"turn_id": turn_id, "queue_wait_ms": queue_wait_ms, "retry_count": turn_snapshot["retry_count"]},
    )
    turn_work_started_at = monotonic()

    payload = turn_snapshot["payload"]
    last_progress_text: str | None = None
    last_progress_at = 0.0
    last_stream_text: str | None = None
    last_stream_at = 0.0
    first_stream_delta_at: float | None = None
    stream_edit_count = 0
    stream_edit_failed = False
    stream_phase_started = False
    status_edit_lock = asyncio.Lock()

    async def edit_progress_status(status_text: str) -> bool:
        async with status_edit_lock:
            if stream_phase_started:
                return False
            return await edit_turn_status_message(user=user, turn=turn, status_text=status_text)

    async def on_progress(status_text: str) -> None:
        nonlocal last_progress_at, last_progress_text
        status_text = _user_visible_progress_text(status_text)
        if not status_text:
            return
        now = monotonic()
        if status_text == last_progress_text:
            return
        if last_progress_text is not None and now - last_progress_at < 1.0:
            return
        last_progress_text = status_text
        last_progress_at = now
        await edit_progress_status(status_text)

    async def on_reply_delta(visible_text: str) -> None:
        nonlocal first_stream_delta_at, last_stream_at, last_stream_text
        nonlocal stream_edit_count, stream_edit_failed, stream_phase_started
        if stream_edit_failed or not settings.telegram_stream_final_replies or not turn_snapshot["status_message_id"]:
            return
        status_text = telegram_plain_text(visible_text).strip()
        if not status_text or status_text == last_stream_text:
            return
        max_chars = max(256, min(4000, settings.telegram_stream_max_chars))
        status_text = status_text[:max_chars]
        now = monotonic()
        if last_stream_text is not None:
            grew_by = len(status_text) - len(last_stream_text)
            interval = max(0.5, settings.telegram_stream_edit_interval_seconds)
            min_chars = max(1, settings.telegram_stream_min_chars)
            if now - last_stream_at < interval or grew_by < min_chars:
                return
        stream_phase_started = True
        async with status_edit_lock:
            ok = await edit_turn_status_message(user=user, turn=turn, status_text=status_text)
        if not ok:
            stream_edit_failed = True
            return
        if first_stream_delta_at is None:
            first_stream_delta_at = now
        last_stream_text = status_text
        last_stream_at = now
        stream_edit_count += 1

    reply_delta_callback = (
        on_reply_delta
        if settings.telegram_stream_final_replies and turn_snapshot["status_message_id"]
        else None
    )
    heartbeat_task = None
    if getattr(settings, "telegram_progress_heartbeat_enabled", True):
        heartbeat_task = asyncio.create_task(
            _run_turn_progress_heartbeat(
                settings=settings,
                user=user,
                turn=turn,
                started_at=turn_work_started_at,
                stream_started=lambda: stream_phase_started,
                current_progress_text=lambda: last_progress_text,
                edit_progress_status=edit_progress_status,
            )
        )

    async def stop_heartbeat() -> None:
        if heartbeat_task is None:
            return
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 — heartbeat is best-effort observability/UI
            log.exception("telegram progress heartbeat failed during shutdown")

    result = None
    assistant_error: Exception | None = None
    try:
        async with session_scope() as session:
            result = await AssistantOrchestrator(session).handle_user_message(
                telegram_user_id=user_snapshot["telegram_user_id"],
                telegram_chat_id=turn_snapshot["telegram_chat_id"],
                telegram_message_id=turn_snapshot["primary_message_id"],
                text=str(payload.get("text") or turn_snapshot["input_text"] or ""),
                username=user_snapshot["username"],
                first_name=user_snapshot["first_name"],
                last_name=user_snapshot["last_name"],
                message_context=payload,
                on_progress=on_progress,
                on_reply_delta=reply_delta_callback,
                touch_last_seen=False,
            )
    except Exception as exc:  # noqa: BLE001
        log.exception("assistant turn failed", fields={"turn_id": turn_id})
        assistant_error = exc
    finally:
        await stop_heartbeat()

    if assistant_error is not None:
        next_turn = None
        async with session_scope() as session:
            next_turn = await TurnService(session).fail_turn(parsed_turn_id, str(assistant_error))
        await send_turn_reply(
            user=user,
            turn=turn,
            reply_text="Что-то пошло не так на моей стороне. Сообщение сохранено, попробуй еще раз.",
            buttons=[],
        )
        if next_turn is not None:
            await _enqueue_turn(next_turn)
        return f"turn failed: {assistant_error}"

    assert result is not None

    if result.agent_run_id is not None and queue_wait_ms is not None:
        async with session_scope() as session:
            run = await session.get(AgentRun, result.agent_run_id)
            if run is not None:
                metadata = run.metadata_ or {}
                latency_ms = dict(metadata.get("latency_ms") or {})
                latency_ms["queue_wait_ms"] = queue_wait_ms
                stream_stats = dict(metadata.get("telegram_streaming") or {})
                if first_stream_delta_at is not None:
                    stream_stats["first_reply_delta_ms"] = max(
                        0,
                        int((first_stream_delta_at - turn_work_started_at) * 1000),
                    )
                stream_stats["edit_count"] = stream_edit_count
                stream_stats["edit_failed"] = stream_edit_failed
                run.metadata_ = {**metadata, "latency_ms": latency_ms, "telegram_streaming": stream_stats}

    if result.reply_rich_html or result.open_app_button or result.open_app_button_label:
        delivered = await send_turn_reply(
            user=user,
            turn=turn,
            reply_text=result.reply_text,
            buttons=result.buttons,
            reply_rich_html=result.reply_rich_html,
            open_app_button=result.open_app_button,
            open_app_button_label=result.open_app_button_label,
        )
    else:
        delivered = await send_turn_reply(
            user=user,
            turn=turn,
            reply_text=result.reply_text,
            buttons=result.buttons,
        )
    if not delivered:
        next_turn = None
        retry_turn = None
        async with session_scope() as session:
            turns = TurnService(session)
            current = await session.get(AssistantTurn, parsed_turn_id)
            if current is None:
                return "turn missing"
            delivery_exhausted = current.retry_count + 1 >= settings.telegram_turn_max_retries
            if delivery_exhausted:
                next_turn = await turns.fail_turn(parsed_turn_id, "telegram delivery failed")
            else:
                retry_turn = await turns.retry_turn(
                    parsed_turn_id,
                    "telegram delivery failed",
                    delay_seconds=_delivery_retry_delay(settings, current.retry_count + 1),
                )
        if next_turn is not None:
            await _enqueue_turn(next_turn)
            return "turn delivery failed"
        if delivery_exhausted:
            return "turn delivery failed"
        if retry_turn is not None:
            await _enqueue_turn(retry_turn)
        return "turn delivery retry scheduled"

    if result.needs_compaction:
        await enqueue_job(
            "compact_conversation",
            str(user_snapshot["id"]),
            conversation_id=str(turn_snapshot["conversation_id"]),
            trigger="system",
            notify=False,
        )

    async with session_scope() as session:
        next_turn = await TurnService(session).complete_turn(parsed_turn_id)
    if next_turn is not None:
        await _enqueue_turn(next_turn)
    return "turn completed"


async def enqueue_due_assistant_turns(ctx: dict[str, Any]) -> str:
    enqueued = 0
    async with session_scope() as session:
        lease_seconds = max(30, get_settings().scheduler_tick_seconds * 2)
        turns = await TurnService(session).reserve_due_turns(limit=100, lease_seconds=lease_seconds)
        turn_ids = [str(turn.id) for turn in turns]
    for turn_id in turn_ids:
        job_id = await _enqueue_turn_id(turn_id)
        if job_id:
            enqueued += 1
    return f"enqueued {enqueued} assistant turns"


@_job(AgentRunType.DAILY_PLANNING)
async def run_daily_planning(*, session, user: User, run: AgentRun, notify: bool,
                             plan_date: str = "", planning_mode="today",
                             request_id: str = "") -> str:
    from datetime import datetime as _dt

    from lumi.assistant.orchestrator import Button
    from lumi.services.notifier import send_telegram_message
    from lumi.services.planning import PlanningService
    from lumi.utils.time import get_zone

    day = None
    if plan_date:
        try:
            parsed = _dt.fromisoformat(plan_date)
            # Anchor at local noon so day-bounds resolve to the right date.
            day = parsed.replace(hour=12, tzinfo=get_zone(user.timezone))
        except ValueError:
            day = None
    summary, created = await PlanningService(session).propose_day_plan(
        user,
        day=day,
        mode=planning_mode,
        request_id=request_id or None,
        agent_run_id=run.id,
    )
    if notify:
        if created:
            language = _run_reply_language(run, user)
            rendered = render_schedule_message(
                title=schedule_plan_title(
                    language=language,
                    start_at=created[0].start_at,
                    timezone=user.timezone,
                ),
                items=[
                    ScheduleMessageItem(
                        title=e.title,
                        start_at=e.start_at,
                        end_at=e.end_at,
                        kind="proposed",
                        action_id=str(e.id),
                    )
                    for e in created
                ],
                timezone=user.timezone,
                language=language,
                confirm_proposed=True,
            )
            reply_markup = markup_from_buttons([
                [
                    Button(text=button.text, callback_data=button.callback_data)
                    for button in row
                ]
                for row in rendered.buttons
            ])
            await send_telegram_message(
                user,
                rendered.plain_text,
                rich_html=rendered.rich_html,
                reply_markup=reply_markup,
                open_app_button=True,
            )
        else:
            await send_telegram_message(user, summary)
    return f"plan: {len(created)} blocks proposed"


@_job(AgentRunType.CALENDAR_SYNC)
async def run_calendar_sync(*, session, user: User, run: AgentRun, notify: bool) -> str:
    from lumi.connectors.google.auth import GoogleNotConnectedError
    from lumi.services.notifier import send_telegram_message
    from lumi.services.planning import CalendarSyncService

    try:
        results = await CalendarSyncService(session).sync_all_calendars(user)
    except GoogleNotConnectedError:
        if notify:
            await send_telegram_message(
                user,
                "Внешний календарь не подключен — внутренний календарь продолжает работать. "
                "Подключить Google или Яндекс можно в Mini App → Settings.",
            )
        return "no external calendar connected"
    parts = []
    for provider, value in results.items():
        label = {"google": "Google", "yandex": "Яндекс"}.get(provider, provider)
        parts.append(f"{label}: {value if isinstance(value, int) else 'ошибка'}")
    summary = "synced " + ", ".join(f"{k}={v}" for k, v in results.items())
    if notify:
        await send_telegram_message(
            user, "Календарь синхронизирован. Событий за 14 дней — " + "; ".join(parts) + "."
        )
    return summary


@_job(AgentRunType.CUSTOM)
async def summarize_calendar_private_note(
    *,
    session,
    user: User,
    run: AgentRun,
    notify: bool,
    event_id: str = "",
    private_note_hash: str = "",
) -> str:
    from lumi.assistant.prompts import CALENDAR_PRIVATE_NOTE_SUMMARY_SYSTEM
    from lumi.db.models import CalendarEvent
    from lumi.services.calendar import CalendarService, private_note_needs_summary

    if not event_id or not private_note_hash:
        return "missing event id or note hash"
    result = await session.execute(
        select(CalendarEvent).where(CalendarEvent.id == uuid.UUID(event_id), CalendarEvent.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if event is None:
        return "event not found"
    metadata = event.metadata_ or {}
    note = metadata.get("private_note")
    if metadata.get("private_note_hash") != private_note_hash:
        return "stale personal note hash"
    if not isinstance(note, str) or not note.strip():
        return "personal note missing"
    if metadata.get("private_note_summary_status") == "ready" and metadata.get("private_note_summary"):
        return "summary already ready"
    calendar = CalendarService(session)
    if not private_note_needs_summary(note):
        await calendar.set_private_note(user, event, note)
        return "summary not needed"
    try:
        response = await LLMGateway().complete_json(
            messages=[LLMMessage(role="user", content=f"Personal note:\n{note}")],
            system=CALENDAR_PRIVATE_NOTE_SUMMARY_SYSTEM,
            json_schema_hint={
                "type": "object",
                "properties": {"summary": {"type": "string", "maxLength": 160}},
                "required": ["summary"],
                "additionalProperties": False,
            },
            temperature=0.1,
            max_tokens=256,
            request_kind="calendar_private_note_summary",
            user_id=user.id,
            agent_run_id=run.id,
            session=session,
        )
    except Exception as exc:  # noqa: BLE001 - note stays usable through deterministic fallback
        await calendar.mark_private_note_summary_failed(
            user,
            event,
            note_hash=private_note_hash,
            error=str(exc),
        )
        return f"summary failed: {exc}"
    await calendar.write_private_note_summary(
        user,
        event,
        note_hash=private_note_hash,
        summary=str(response.get("summary") or ""),
    )
    return f"summarized {event.id}"


@_job(AgentRunType.CUSTOM)
async def extract_focus_reflection(
    *,
    session,
    user: User,
    run: AgentRun,
    notify: bool,
    analysis_id: str = "",
) -> str:
    del run, notify
    if not analysis_id:
        return "missing reflection analysis id"
    from lumi.services.reflection_analysis import ReflectionAnalysisService

    analysis = await ReflectionAnalysisService(session).process(
        user_id=user.id,
        analysis_id=uuid.UUID(analysis_id),
    )
    if analysis is None:
        return "reflection analysis not found"
    return f"reflection analysis {analysis.status.value}"


@_job(AgentRunType.COMPACTION)
async def compact_conversation(*, session, user: User, run: AgentRun, notify: bool,
                               conversation_id: str = "") -> str:
    from lumi.assistant.compaction import CompactionService

    result = await session.execute(
        select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return "conversation not found"
    summary = await CompactionService(session).compact(user, conversation, agent_run_id=run.id)
    return f"compacted {summary.message_count} messages" if summary else "nothing to compact"


# ---------------------------------------------------------------------------
# Reminders (cron, every minute)
# ---------------------------------------------------------------------------

async def send_due_reminders(ctx: dict[str, Any]) -> str:
    """arq cron job: find due reminders across users and notify."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from lumi.services.notifier import send_telegram_message
    from lumi.services.tasks import TaskService

    sent = 0
    async with session_scope() as session:
        tasks_service = TaskService(session)
        due = await tasks_service.find_due_reminders()
        for task in due:
            result = await session.execute(select(User).where(User.id == task.user_id))
            user = result.scalar_one_or_none()
            if user is None:
                continue
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✓ Выполнено", callback_data=f"task_done:{task.id}"),
                InlineKeyboardButton(text="⏰ Через час", callback_data=f"task_snooze:{task.id}:1h"),
                InlineKeyboardButton(text="📅 Завтра", callback_data=f"task_snooze:{task.id}:tomorrow"),
            ]])
            text = f"⏰ Напоминание: {task.title}"
            if task.due_at:
                text += f"\nСрок: {fmt_local(task.due_at, user.timezone)}"
            send_result = await send_telegram_message(
                user,
                text,
                reply_markup=markup,
                capture_message_ids=True,
            )
            if send_result:
                telegram_message_ids = send_result if isinstance(send_result, list) else []
                await _record_task_reminder_notification(
                    session=session,
                    user=user,
                    task=task,
                    text=text,
                    telegram_message_ids=telegram_message_ids,
                )
                await tasks_service.mark_reminder_sent(task)
                sent += 1
    if sent:
        log.info("reminders sent", fields={"count": sent})
    return f"sent {sent}"


async def _record_task_reminder_notification(
    *,
    session,
    user: User,
    task: Task,
    text: str,
    telegram_message_ids: list[int],
) -> None:
    conversation = await UserService(session).ensure_main_conversation(user)
    telegram_message_id = telegram_message_ids[-1] if telegram_message_ids else None
    content_json = {
        "notification_type": "task_reminder",
        "task_id": str(task.id),
        "task_title": task.title,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "reminder_at": task.reminder_at.isoformat() if task.reminder_at else None,
        "telegram_message_id": telegram_message_id,
        "telegram_message_ids": telegram_message_ids,
    }
    session.add(Message(
        conversation_id=conversation.id,
        user_id=user.id,
        role=MessageRole.ASSISTANT,
        content=text,
        content_json=content_json,
        char_count=len(text),
        telegram_chat_id=user.telegram_chat_id or user.telegram_user_id,
        telegram_message_id=telegram_message_id,
        metadata_=content_json,
    ))


async def cleanup_ui_events(ctx: dict[str, Any]) -> str:
    """Delete realtime outbox events after the reconnect catch-up window."""
    from lumi.services.realtime import RealtimeEventService

    async with session_scope() as session:
        deleted = await RealtimeEventService(session).delete_older_than(
            utc_now() - timedelta(hours=72)
        )
    return f"deleted {deleted}"


async def process_due_opportunity_jobs(ctx: dict[str, Any]) -> str:
    """arq cron job: precompute low-latency task/review suggestions for due users."""
    processed = 0
    now = utc_now()
    async with session_scope() as session:
        result = await session.execute(
            select(AssistantOpportunityJob)
            .where(
                AssistantOpportunityJob.next_check_at <= now,
                (
                    AssistantOpportunityJob.locked_until.is_(None)
                    | (AssistantOpportunityJob.locked_until <= now)
                ),
            )
            .order_by(AssistantOpportunityJob.next_check_at.asc())
            .limit(20)
            .with_for_update(skip_locked=True)
        )
        jobs = list(result.scalars())
        for job in jobs:
            job.locked_until = now + timedelta(seconds=60)
        await session.flush()

        for job in jobs:
            user = await _load_user(session, str(job.user_id))
            if user is None:
                job.locked_until = None
                job.next_check_at = now + timedelta(hours=1)
                continue
            created = await _process_opportunity_job(session, user, job)
            job.last_run_at = now
            job.locked_until = None
            job.next_check_at = now + _next_opportunity_delay(job.kind)
            if created:
                processed += 1
    if processed:
        log.info("opportunity jobs processed", fields={"count": processed})
    return f"processed {processed}"


async def enqueue_active_user_task_cleanup(ctx: dict[str, Any]) -> str:
    """Queue light cleanup for users who recently opened/chat with Lumi."""
    now = utc_now()
    cutoff = now - timedelta(hours=24)
    queued = 0
    async with session_scope() as session:
        result = await session.execute(
            select(User)
            .where(User.last_seen_at.is_not(None), User.last_seen_at >= cutoff)
            .order_by(User.last_seen_at.desc())
            .limit(200)
        )
        service = AssistantSuggestionService(session)
        for user in result.scalars():
            await service.enqueue_opportunity(
                user,
                kind="task_cleanup",
                scope_key="review",
                reason="active_sweep",
                payload={"sweep": "active"},
                delay_seconds=45,
            )
            queued += 1
    return f"queued {queued}"


async def enqueue_daily_task_cleanup(ctx: dict[str, Any]) -> str:
    """Queue one daily deep cleanup close to each user's workday start."""
    now = utc_now()
    queued = 0
    async with session_scope() as session:
        result = await session.execute(
            select(User)
            .where(User.last_seen_at.is_not(None), User.last_seen_at >= now - timedelta(days=14))
            .limit(500)
        )
        service = AssistantSuggestionService(session)
        for user in result.scalars():
            planning = normalize_planning_settings(user.settings)
            local_now = now.astimezone(get_zone(user.timezone))
            if local_now.weekday() not in planning["work_days"]:
                continue
            start_hour = int(str(planning["work_hours"]["start"]).split(":", 1)[0])
            if local_now.hour != start_hour:
                continue
            scope = f"daily:{local_now.date().isoformat()}"
            await service.enqueue_opportunity(
                user,
                kind="task_cleanup",
                scope_key=scope,
                reason="daily_cleanup",
                payload={"date": local_now.date().isoformat(), "sweep": "daily"},
                delay_seconds=60,
            )
            queued += 1
    return f"queued {queued}"


def _next_opportunity_delay(kind: str) -> timedelta:
    if kind == "task_cleanup":
        return timedelta(hours=6)
    if kind == "slot_suggestions":
        return timedelta(hours=1)
    return timedelta(hours=1)


async def _process_opportunity_job(session, user: User, job: AssistantOpportunityJob) -> bool:
    if job.kind == "task_cleanup":
        return await _precompute_task_cleanup(session, user, job=job)
    if job.kind in {"slot_suggestions", "task_suggestions"}:
        return await _precompute_slot_suggestion(session, user, job=job)
    return False


def _review_skips(task: Task) -> dict[str, bool]:
    skips = (task.metadata_ or {}).get("review_skips")
    if not isinstance(skips, dict):
        return {}
    return {str(key): True for key, value in skips.items() if value is True}


def _task_payload(task: Task) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "title": task.title,
        "project": task.project,
        "project_id": str(task.project_id) if task.project_id else None,
        "priority": task.priority.value,
        "tags": task.tags or [],
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "target_at": task.target_at.isoformat() if task.target_at else None,
        "estimated_minutes": task.estimated_minutes,
        "estimate_source": task.estimate_source,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "review_skips": _review_skips(task),
    }


async def _load_open_tasks_for_cleanup(session, user: User) -> list[Task]:
    result = await session.execute(
        select(Task)
        .where(
            Task.user_id == user.id,
            Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX]),
        )
        .order_by(
            Task.due_at.asc().nulls_last(),
            Task.priority.desc(),
            Task.updated_at.desc(),
        )
        .limit(200)
    )
    return list(result.scalars())


def _needs_cleanup(task: Task) -> bool:
    if task.status != TaskStatus.INBOX:
        return False
    skips = _review_skips(task)
    if task.estimated_minutes is None and task.estimate_source != "skipped":
        return True
    if task.due_at is None and not skips.get("due_date"):
        return True
    if task.project_id is None and not skips.get("project"):
        return True
    if task.project == "Backlog" and not skips.get("project"):
        return True
    return False


async def _pending_review_keys(session, user: User) -> set[tuple[str, str]]:
    pending = await AssistantSuggestionService(session).list_pending(user, limit=200)
    keys: set[tuple[str, str]] = set()
    for suggestion in pending:
        task_id = suggestion.payload.get("task_id")
        if isinstance(task_id, str):
            keys.add((suggestion.kind, task_id))
    return keys


async def _precompute_task_cleanup(session, user: User, *, job: AssistantOpportunityJob) -> bool:
    planning = normalize_planning_settings(user.settings)
    if not planning["auto_enrich_tasks"]:
        return False

    tasks = [task for task in await _load_open_tasks_for_cleanup(session, user) if _needs_cleanup(task)]
    if not tasks:
        return False

    pending_keys = await _pending_review_keys(session, user)
    context = {
        "locale": normalize_app_locale(user.locale),
        "timezone": user.timezone,
        "reason": job.reason,
        "tasks": [_task_payload(task) for task in tasks],
        "allowed_decisions": ["task_estimate", "task_due_date", "task_project"],
    }
    try:
        raw = await _task_cleanup_llm(session, user, context)
        for _ in range(2):
            enrichment = await _cleanup_enrichment(session, user, raw.get("enrichment_requests"))
            if not enrichment:
                break
            context = {**context, "enrichment": enrichment}
            raw = await _task_cleanup_llm(session, user, context)
    except LLMError:
        log.exception("task cleanup llm failed", fields={"user_id": str(user.id)})
        return False

    task_by_id = {str(task.id): task for task in tasks}
    created = 0
    for decision in _validated_cleanup_decisions(raw):
        task = task_by_id.get(decision["task_id"])
        if task is None:
            continue
        suggestion = await _create_cleanup_suggestion(
            session,
            user,
            task,
            decision,
            pending_keys=pending_keys,
        )
        if suggestion:
            created += 1
            pending_keys.add((suggestion.kind, str(task.id)))
    return created > 0


async def _task_cleanup_llm(session, user: User, context: dict[str, Any]) -> dict[str, Any]:
    return await LLMGateway().complete_json(
        messages=[LLMMessage(role="user", content=json.dumps(context, ensure_ascii=False))],
        system=(
            "You prepare quiet task cleanup suggestions. Return JSON only. "
            "Never mutate tasks. Prefer high-confidence decisions. "
            "Use no_deadline=true for backlog/someday items that should not get a due date. "
            "If context is insufficient, request enrichment only as "
            "project/backlog/due_window/tag filters; max two rounds."
        ),
        request_kind="task_cleanup",
        user_id=user.id,
        session=session,
        max_tokens=4096,
    )


async def _cleanup_enrichment(session, user: User, raw_requests: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_requests, list):
        return []
    enriched: list[dict[str, Any]] = []
    for request in raw_requests[:2]:
        if not isinstance(request, dict):
            continue
        tasks = await _load_enrichment_tasks(session, user, request)
        if not tasks:
            continue
        enriched.append({
            "request": {key: request[key] for key in ("type", "project", "days", "tag") if key in request},
            "tasks": [_task_payload(task) for task in tasks[:50]],
        })
    return enriched


async def _load_enrichment_tasks(session, user: User, request: dict[str, Any]) -> list[Task]:
    request_type = request.get("type")
    base = [
        Task.user_id == user.id,
        Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX]),
    ]
    if request_type == "project":
        project = request.get("project")
        if not isinstance(project, str) or not project.strip():
            return []
        stmt = select(Task).where(*base, Task.project == project.strip())
    elif request_type == "backlog":
        stmt = select(Task).where(*base, Task.project == "Backlog")
    elif request_type == "due_window":
        days = request.get("days")
        if not isinstance(days, int):
            days = 14
        days = max(1, min(days, 90))
        now = utc_now()
        stmt = select(Task).where(*base, Task.due_at.is_not(None), Task.due_at <= now + timedelta(days=days))
    elif request_type == "tag":
        tag = request.get("tag")
        if not isinstance(tag, str) or not tag.strip():
            return []
        result = await session.execute(
            select(Task)
            .where(*base)
            .order_by(Task.updated_at.desc())
            .limit(200)
        )
        needle = tag.strip().lower()
        return [task for task in result.scalars() if any(str(item).lower() == needle for item in (task.tags or []))]
    else:
        return []

    result = await session.execute(
        stmt.order_by(
            Task.due_at.asc().nulls_last(),
            Task.priority.desc(),
            Task.updated_at.desc(),
        ).limit(50)
    )
    return list(result.scalars())


def _validated_cleanup_decisions(raw: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = raw.get("decisions")
    if not isinstance(raw_items, list):
        return []
    decisions: list[dict[str, Any]] = []
    for item in raw_items[:40]:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        task_id = item.get("task_id")
        if kind not in {"task_estimate", "task_due_date", "task_project"}:
            continue
        if not isinstance(task_id, str) or not task_id:
            continue
        reason = item.get("reason")
        confidence = item.get("confidence")
        decisions.append({
            **item,
            "kind": kind,
            "task_id": task_id,
            "reason": reason if isinstance(reason, str) and reason.strip() else "Prepared by Lumi.",
            "confidence": confidence if confidence in {"low", "medium", "high"} else "medium",
        })
    return decisions


async def _create_cleanup_suggestion(
    session,
    user: User,
    task: Task,
    decision: dict[str, Any],
    *,
    pending_keys: set[tuple[str, str]],
):
    kind = decision["kind"]
    task_id = str(task.id)
    if (kind, task_id) in pending_keys:
        return None
    skips = _review_skips(task)
    reason = decision["reason"]
    confidence = decision["confidence"]
    payload: dict[str, Any] = {
        "task_id": task_id,
        "reason": reason,
        "confidence": confidence,
        "source": "llm",
    }

    if kind == "task_estimate":
        minutes = decision.get("estimated_minutes")
        if task.estimated_minutes is not None or task.estimate_source == "skipped":
            return None
        if not isinstance(minutes, int) or minutes < 1 or minutes > 1440:
            return None
        payload["estimated_minutes"] = minutes
        title = f"Estimate {task.title}"
        description = f"{minutes} min · {reason}"
        context_hash = f"cleanup:estimate:{task.id}:{task.updated_at.isoformat()}:{minutes}"
    elif kind == "task_due_date":
        if task.due_at is not None or skips.get("due_date"):
            return None
        due_at = decision.get("due_at")
        no_deadline = decision.get("no_deadline") is True
        if no_deadline:
            payload["no_deadline"] = True
            payload["bucket"] = decision.get("bucket") if isinstance(decision.get("bucket"), str) else "Someday / Backlog"
            title = f"No deadline for {task.title}"
            description = reason
            context_hash = f"cleanup:due:none:{task.id}:{task.updated_at.isoformat()}"
        else:
            if not isinstance(due_at, str):
                return None
            try:
                parsed = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
            except ValueError:
                return None
            payload["due_at"] = parsed.isoformat()
            payload["bucket"] = decision.get("bucket") if isinstance(decision.get("bucket"), str) else "Likely this week"
            title = f"Plan date for {task.title}"
            description = reason
            context_hash = f"cleanup:due:{task.id}:{task.updated_at.isoformat()}:{parsed.isoformat()}"
    else:
        if skips.get("project"):
            return None
        project = decision.get("project")
        project_id = decision.get("project_id")
        if isinstance(project_id, str) and project_id:
            payload["project_id"] = project_id
            project_label = decision.get("project") if isinstance(decision.get("project"), str) else "Project"
        elif isinstance(project, str) and project.strip():
            project_label = project.strip()
            payload["project"] = project_label
        else:
            return None
        if task.project == project_label and task.project_id is not None:
            return None
        title = f"Sort {task.title}"
        description = reason
        context_hash = f"cleanup:project:{task.id}:{task.updated_at.isoformat()}:{project_label}"

    return await AssistantSuggestionService(session).create(
        user,
        kind=kind,
        title=title,
        description=description,
        payload=payload,
        context_hash=context_hash,
        affected_task_ids=[task_id],
        expires_at=utc_now() + timedelta(days=7),
    )


async def _precompute_slot_suggestion(session, user: User, *, job: AssistantOpportunityJob) -> bool:
    planning = normalize_planning_settings(user.settings)
    if not planning["micro_slots_enabled"]:
        return False

    day = _slot_day(user, job)
    min_minutes = int(planning["micro_slots"]["min_minutes"])
    slots = await CalendarService(session).find_free_slots(user, day=day, duration_minutes=min_minutes)
    if not slots:
        return False

    result = await session.execute(
        select(Task)
        .where(
            Task.user_id == user.id,
            Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX]),
        )
        .order_by(
            Task.due_at.asc().nulls_last(),
            Task.priority.desc(),
            Task.created_at.desc(),
        )
        .limit(200)
    )
    tasks = [task for task in result.scalars() if task.estimated_minutes is not None and task.estimated_minutes >= 1]
    if not tasks:
        return False

    slot_start, slot_end, picked, source, reason = await _rank_slot_tasks(session, user, slots, tasks)
    if not picked:
        return False
    total = sum(task.estimated_minutes or 0 for task in picked)
    context_hash = "slot_suggestions:" + "|".join([
        slot_start.isoformat(),
        slot_end.isoformat(),
        *[f"{task.id}:{task.updated_at.isoformat()}:{task.estimated_minutes}" for task in picked],
    ])
    first_project = picked[0].project
    locale = normalize_app_locale(user.locale)
    english_task_label = "quick win" if len(picked) == 1 else "quick wins"
    description = (
        f"Lumi already picked {len(picked)} {english_task_label} for {total} min"
        if locale == "en"
        else f"Lumi уже подобрала {len(picked)} {ru_plural(len(picked), 'задачу', 'задачи', 'задач')} на {total} мин"
    )
    await AssistantSuggestionService(session).create(
        user,
        kind="micro_slot",
        title=f"{int((slot_end - slot_start).total_seconds() // 60)} min free",
        description=description,
        start_at=slot_start,
        end_at=slot_end,
        payload={
            "slot": {"start_at": slot_start.isoformat(), "end_at": slot_end.isoformat()},
            "tasks": [
                {
                    "id": str(task.id),
                    "title": task.title,
                    "project": task.project,
                    "estimated_minutes": task.estimated_minutes,
                    "priority": task.priority.value,
                }
                for task in picked
            ],
            "project": first_project,
            "reason": reason,
            "source": source,
        },
        context_hash=context_hash,
        affected_task_ids=[str(task.id) for task in picked],
        expires_at=utc_now() + timedelta(hours=4),
    )
    return True


def _slot_day(user: User, job: AssistantOpportunityJob):
    raw_date = (job.payload or {}).get("date")
    if isinstance(raw_date, str) and raw_date:
        try:
            parsed = datetime.fromisoformat(raw_date)
        except ValueError:
            parsed = utc_now()
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=get_zone(user.timezone))
        return parsed
    return utc_now()


async def _rank_slot_tasks(
    session,
    user: User,
    slots: list[tuple[datetime, datetime]],
    tasks: list[Task],
) -> tuple[datetime, datetime, list[Task], str, str]:
    tasks.sort(key=lambda task: (
        task.due_at is None,
        task.estimated_minutes or 999,
        -task.created_at.timestamp(),
    ))
    for slot_start, slot_end in slots:
        slot_minutes = int((slot_end - slot_start).total_seconds() // 60)
        fitting = [task for task in tasks if (task.estimated_minutes or 9999) <= min(slot_minutes, 30)]
        if not fitting:
            continue
        ranked = fitting[:8]
        try:
            raw = await LLMGateway().complete_json(
                messages=[LLMMessage(role="user", content=json.dumps({
                    "slot": {"start_at": slot_start.isoformat(), "end_at": slot_end.isoformat(), "minutes": slot_minutes},
                    "tasks": [_task_payload(task) for task in ranked],
                }, ensure_ascii=False))],
                system=(
                    "Rank tasks for this free calendar slot. Return JSON only with "
                    "task_ids ordered best-first and a short reason."
                ),
                request_kind="slot_suggestions",
                user_id=user.id,
                session=session,
                max_tokens=2048,
            )
            ordered_ids = raw.get("task_ids")
            picked_by_id = {str(task.id): task for task in ranked}
            picked = [
                picked_by_id[task_id]
                for task_id in ordered_ids[:3]
                if isinstance(task_id, str) and task_id in picked_by_id
            ] if isinstance(ordered_ids, list) else []
            if picked:
                reason = raw.get("reason")
                return slot_start, slot_end, picked, "llm", reason if isinstance(reason, str) else "Fits this free window."
        except LLMError:
            log.exception("slot suggestion llm failed", fields={"user_id": str(user.id)})
        return slot_start, slot_end, ranked[:3], "heuristic", "Fits this free window."
    return slots[0][0], slots[0][1], [], "heuristic", "No fitting task."


async def recover_pending_calendar_private_note_summaries(ctx: dict[str, Any]) -> str:
    """Cron recovery when an API enqueue races commit or Redis is temporarily down."""
    from lumi.db.models import CalendarEvent

    async with session_scope() as session:
        result = await session.execute(
            select(CalendarEvent)
            .where(CalendarEvent.metadata_["private_note_summary_status"].astext == "pending")
            .order_by(CalendarEvent.updated_at)
            .limit(50)
        )
        events = list(result.scalars())
        enqueued = 0
        for event in events:
            note_hash = (event.metadata_ or {}).get("private_note_hash")
            if not note_hash:
                continue
            job_id = await enqueue_job(
                "summarize_calendar_private_note",
                str(event.user_id),
                event_id=str(event.id),
                private_note_hash=note_hash,
                notify=False,
            )
            if job_id:
                enqueued += 1
    return f"enqueued {enqueued} calendar personal note summaries"


async def recover_focus_reflection_analyses(ctx: dict[str, Any]) -> str:
    """Retry durable pending/failed rows and reclaim stale running leases."""

    del ctx
    from sqlalchemy import or_

    from lumi.db.models import FocusAnalysisStatus, FocusSessionAnalysis

    now = utc_now()
    stale_before = now - timedelta(minutes=15)
    async with session_scope() as session:
        result = await session.execute(
            select(FocusSessionAnalysis)
            .where(
                or_(
                    FocusSessionAnalysis.status == FocusAnalysisStatus.PENDING,
                    (
                        (FocusSessionAnalysis.status == FocusAnalysisStatus.FAILED)
                        & (FocusSessionAnalysis.next_retry_at <= now)
                    ),
                    (
                        (FocusSessionAnalysis.status == FocusAnalysisStatus.RUNNING)
                        & (FocusSessionAnalysis.updated_at <= stale_before)
                    ),
                )
            )
            .order_by(FocusSessionAnalysis.updated_at)
            .limit(50)
        )
        rows = list(result.scalars())
        enqueued = 0
        for analysis in rows:
            if analysis.status == FocusAnalysisStatus.RUNNING:
                analysis.status = FocusAnalysisStatus.PENDING
            job_id = await enqueue_job(
                "extract_focus_reflection",
                str(analysis.user_id),
                analysis_id=str(analysis.id),
                notify=False,
            )
            if job_id:
                enqueued += 1
    return f"enqueued {enqueued} focus reflection analyses"


JOB_BY_AUTOMATION_TYPE = {
    "calendar_sync": "run_calendar_sync",
}

AGENT_RUN_TYPE_BY_AUTOMATION = {
    "calendar_sync": AgentRunType.CALENDAR_SYNC,
}
