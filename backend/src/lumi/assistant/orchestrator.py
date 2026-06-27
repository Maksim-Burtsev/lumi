"""AssistantOrchestrator: the chat pipeline.

save message -> extract signals -> apply safe actions -> build context ->
final LLM reply -> save reply -> (maybe) compaction flag.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from difflib import SequenceMatcher
from html import escape
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.action_reply_renderer import ActionOutcome, ActionReplyRenderer
from lumi.assistant.context_builder import ContextBuilder, PlannerContext, PlannerContextBuilder
from lumi.assistant.media import ImageInput, MediaCandidate, media_candidate_id
from lumi.assistant.media_understanding import (
    FocusedVisionService,
    MediaReferenceService,
    MediaUnderstandingService,
)
from lumi.assistant.memory_service import MemoryService
from lumi.assistant.planner import AgentPlanner
from lumi.assistant.schemas import (
    AgentPlan,
    AutomationRequest,
    BulkTaskPatchRequest,
    CalendarEventsRequest,
    CalendarRequest,
    EmailRequest,
    ExtractedTask,
    FocusedVisionRequest,
    MediaUnderstanding,
    MemoryCandidate,
    NewsRequest,
    PlannedToolCall,
    TaskPatchRequest,
    TaskUpdate,
)
from lumi.bot.schedule_messages import (
    render_schedule_message,
    schedule_items_from_calendar_events,
    schedule_window_title,
)
from lumi.db.models import (
    AgentRunType,
    CalendarEventStatus,
    Message,
    MessageRole,
    Task,
    TaskStatus,
    User,
)
from lumi.i18n import (
    ensure_language_settings,
    format_language_settings_reply,
    normalize_reply_language,
    normalize_reply_language_mode,
    validate_app_locale,
)
from lumi.llm.gateway import LLMGateway
from lumi.logging import agent_run_id_var, get_logger
from lumi.services.calendar import CalendarService, merge_busy_intervals
from lumi.services.confirmations import ConfirmationService
from lumi.services.planning import CalendarSyncService, PlanningService
from lumi.services.realtime import RealtimeEventService, commit_with_realtime
from lumi.services.runs import RunService
from lumi.services.task_update_replies import (
    format_task_bulk_update_reply,
    format_task_update_ambiguous_reply,
    format_task_update_choice_prompt,
    format_task_update_confirmation_prompt,
    format_task_update_no_updates_reply,
    format_task_update_not_found_reply,
    format_task_update_reply,
)
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.utils.text import truncate
from lumi.utils.time import fmt_local, local_now, local_to_utc, utc_now, utc_to_local
from lumi.worker.queue import enqueue_job

log = get_logger(__name__)

TASK_AUTO_CREATE_CONFIDENCE = 0.85
TASK_CONFIRM_CONFIDENCE = 0.5
MEMORY_EXPLICIT_CONFIDENCE = 0.85
MEMORY_IMPLICIT_CONFIDENCE = 0.92
FALLBACK_REPLY = (
    "The model is unavailable right now. I saved your message. Please try again in a minute."
)
FOCUSED_VISION_UNSAFE_REPLY = (
    "I cannot safely do that from the image. Please clarify exactly what to inspect."
)
MEDIA_REQUIRED_REPLY = "Send an image or reply to the image you want me to inspect."
IMAGE_SOURCED_CONFIRM_TOOLS = {
    "create_task",
    "update_task",
    "bulk_update_tasks",
    "rename_task",
    "complete_task",
    "snooze_task",
    "store_memory",
    "create_internal_calendar_block",
    "create_external_calendar_event",
    "create_automation",
}
AGENT_LOOP_MAX_MODEL_STEPS = 4
AGENT_LOOP_MAX_TOOL_CALLS = 8
CALENDAR_TELEGRAM_EVENT_LIMIT = 5
CALENDAR_TELEGRAM_FREE_GAP_MINUTES = 15
NEUTRAL_PROGRESS_STATUS = "⏳"
READ_ONLY_LOOP_TOOLS = {"read_tasks", "read_calendar_events"}
MULTI_STEP_INTENT_MARKERS = (
    "add",
    "after",
    "block",
    "create",
    "schedule",
    "until",
    "добав",
    "созд",
    "заплан",
    "блок",
    "после",
    "aggiungi",
    "crea",
    "blocco",
    "dopo",
    "riunione",
    "finché",
    "finche",
)
SCHEDULE_READ_KEYWORDS = (
    r"\bschedule\b",
    r"\bcalendar\b",
    r"\bagenda\b",
    r"\bmeetings?\b",
    r"\bevents?\b",
    r"распис",
    r"календар",
    r"встреч",
    r"событ",
)
SCHEDULE_DATE_REF_KEYWORDS = (
    r"\btoday\b",
    r"\btomorrow\b",
    r"\bweek\b",
    r"сегодня",
    r"завтра",
    r"недел",
)
SCHEDULE_CONTEXT_KEYWORDS = (
    *SCHEDULE_READ_KEYWORDS,
    r"external calendar sync",
    r"scheduled events",
    r"событ[ийя].*календар",
    r"внешн.*синхронизац",
)
SCHEDULE_MUTATION_KEYWORDS = (
    r"\bschedule\s+(?:a|an|the|my|our)?\s*(?:meeting|call|event|block|focus|task|appointment)\b",
    r"\bbook\s+(?:a|an|the)?\s*(?:meeting|call|event|appointment)\b",
    r"\bcreate\s+(?:a|an|the)?\s*(?:meeting|call|event|block|focus|task|appointment)\b",
    r"\badd\s+(?:a|an|the)?\s*(?:meeting|call|event|block|focus|task|appointment)\b",
    r"заплан",
    r"созд",
    r"добав",
    r"назнач",
    r"заброни",
)
WEEKDAY_ALIASES = {
    0: (r"\bmonday\b", r"\bmon\b", r"понедельник", r"\bпн\b"),
    1: (r"\btuesday\b", r"\btue\b", r"вторник", r"\bвт\b"),
    2: (r"\bwednesday\b", r"\bwed\b", r"сред", r"\bср\b"),
    3: (r"\bthursday\b", r"\bthu\b", r"четверг", r"\bчт\b"),
    4: (r"\bfriday\b", r"\bfri\b", r"пятниц", r"\bпт\b"),
    5: (r"\bsaturday\b", r"\bsat\b", r"суббот", r"\bсб\b"),
    6: (r"\bsunday\b", r"\bsun\b", r"воскрес", r"\bвс\b"),
}
FLEXIBLE_CALENDAR_SLOT_MARKERS = (
    "after",
    "first free",
    "free slot",
    "without overlap",
    "без налож",
    "после",
    "свобод",
    "окно",
    "dopo",
    "spazio libero",
    "senza sovrapp",
)
ImageLoader = Callable[[dict], Awaitable[ImageInput | None]]


@dataclass(slots=True)
class Button:
    text: str
    callback_data: str
    key: str | None = None


@dataclass(slots=True)
class AssistantResult:
    reply_text: str
    buttons: list[list[Button]] = field(default_factory=list)
    agent_run_id: uuid.UUID | None = None
    needs_compaction: bool = False
    open_app_button: bool = False
    open_app_button_label: str | None = None
    reply_rich_html: str | None = None


@dataclass(slots=True)
class ToolLoopResult:
    plan: AgentPlan
    action_results: list[str]
    action_outcomes: list[ActionOutcome]
    buttons: list[list[Button]]
    reply_rich_html: str | None
    open_app_button: bool
    use_action_reply_renderer: bool
    stop_reason: str
    observations: list[dict[str, Any]]


@dataclass(slots=True)
class CalendarReadResult:
    observation_summary: str
    reply_rich_html: str | None = None
    open_app_button: bool = False


def _rename_choice_button_text(task: Task) -> str:
    parts = [truncate(task.title, 56)]
    if task.project:
        parts.append(task.project)
    parts.extend(f"#{tag.lstrip('#')}" for tag in (task.tags or []) if tag)
    return " · ".join(parts)


def _rename_choice_callback(confirmation_id: uuid.UUID, index: int) -> str:
    return f"rename_pick:{confirmation_id.hex[:12]}:{index}"


def _update_choice_callback(confirmation_id: uuid.UUID, index: int) -> str:
    return f"update_pick:{confirmation_id.hex[:12]}:{index}"


def _snooze_choice_callback(confirmation_id: uuid.UUID, index: int) -> str:
    return f"snooze_pick:{confirmation_id.hex[:12]}:{index}"


def _args_with_call_defaults(call: PlannedToolCall) -> dict:
    args = dict(call.args)
    args.setdefault("confidence", call.confidence)
    if _image_sourced_write(call):
        args["requires_confirmation"] = True
    else:
        args.setdefault("requires_confirmation", call.requires_confirmation)
    return args


def _is_reopen_task_update(patch: TaskPatchRequest) -> bool:
    return patch.update_fields().get("status") in {"active", "inbox"}


def _image_sourced_write(call: PlannedToolCall) -> bool:
    return call.source in {"image", "mixed"} and call.name in IMAGE_SOURCED_CONFIRM_TOOLS


def _call_source_payload(call: PlannedToolCall) -> dict:
    payload: dict = {}
    if call.source != "text":
        payload["_source"] = call.source
    if call.evidence:
        payload["_evidence"] = call.evidence
    return payload


def _prompt_with_evidence(prompt: str, call: PlannedToolCall) -> str:
    if call.source == "text" or not call.evidence:
        return prompt
    facts = "\n".join(f"- {fact}" for fact in call.evidence[:6])
    return f"{prompt}\nExtracted from image:\n{facts}"


def _calendar_request_from_tool_call(call: PlannedToolCall) -> CalendarRequest:
    kind = {
        "plan_day": "plan_day",
        "find_focus_slot": "find_focus_slot",
        "create_internal_calendar_block": "create_internal_block",
        "create_external_calendar_event": "create_external_event",
    }[call.name]
    return CalendarRequest.model_validate({
        "kind": kind,
        **_args_with_call_defaults(call),
    })


def _task_query_from_call(call: PlannedToolCall) -> str:
    query = str(call.args.get("task_query") or call.args.get("current_title") or "").strip()
    return query or "—"


def _media_context_from_payload(payload: object) -> MediaUnderstanding | None:
    if not payload:
        return None
    try:
        return MediaUnderstanding.model_validate(payload)
    except Exception:  # noqa: BLE001
        return None


def _find_media_candidate(media_id: str | None, candidates: list[MediaCandidate]) -> MediaCandidate | None:
    if not media_id:
        return None
    normalized = " ".join(media_id.split()).strip()
    candidate_keys: list[tuple[MediaCandidate, set[str], set[str]]] = []
    for candidate in candidates:
        raw_keys = {
            str(candidate.metadata.get("file_unique_id") or ""),
            str(candidate.metadata.get("file_id") or ""),
            str(candidate.metadata.get("telegram_message_id") or ""),
        }
        raw_keys.discard("")
        all_keys = {candidate.id, *raw_keys, *(f"{candidate.source}:{key}" for key in raw_keys)}
        candidate_keys.append((candidate, raw_keys, all_keys))

    for candidate, _, all_keys in candidate_keys:
        if normalized in all_keys:
            return candidate

    # M3 can preserve the Telegram identifier but swap the transient source prefix
    # (for example attached:<file_unique_id> vs recent:<file_unique_id>).
    suffix = normalized.split(":", 1)[1] if ":" in normalized else normalized
    for candidate, raw_keys, _ in candidate_keys:
        if suffix in raw_keys:
            return candidate
        if any(normalized.endswith(f":{key}") for key in raw_keys):
            return candidate

    if len(suffix) >= 8:
        best: tuple[float, MediaCandidate] | None = None
        second_score = 0.0
        for candidate, raw_keys, all_keys in candidate_keys:
            comparable = raw_keys | all_keys
            score = max(SequenceMatcher(None, suffix, key).ratio() for key in comparable if len(key) >= 8)
            if best is None or score > best[0]:
                if best is not None:
                    second_score = max(second_score, best[0])
                best = (score, candidate)
            else:
                second_score = max(second_score, score)
        if best is not None and best[0] >= 0.92 and best[0] - second_score >= 0.03:
            return best[1]
    return None


def _dedupe_media_candidates(candidates: list[MediaCandidate]) -> list[MediaCandidate]:
    seen: set[str] = set()
    deduped: list[MediaCandidate] = []
    for candidate in candidates:
        key = candidate.metadata.get("file_unique_id") or candidate.metadata.get("file_id") or candidate.id
        if key in seen:
            continue
        seen.add(str(key))
        deduped.append(candidate)
    return deduped


def _selected_or_current_media(
    plan: AgentPlan,
    candidates: list[MediaCandidate],
    current: MediaCandidate | None,
) -> MediaCandidate | None:
    return _find_media_candidate(plan.referenced_media_id, candidates) or current


def _image_write_policy_violations(plan: AgentPlan) -> list[PlannedToolCall]:
    if plan.visual_intent == "action_evidence":
        return []
    return [call for call in plan.tool_calls if _image_sourced_write(call)]


def _reply_result(reply_text: str, *, run_id: uuid.UUID, needs_compaction: bool) -> AssistantResult:
    return AssistantResult(
        reply_text=reply_text,
        agent_run_id=run_id,
        needs_compaction=needs_compaction,
    )


def _reply_language_for_turn(user: User, text: str, planner_language: str | None) -> str:
    language_settings = ensure_language_settings(user.settings)
    mode = language_settings.get("reply_language_mode")
    if mode == "fixed":
        return normalize_reply_language(str(language_settings.get("reply_language") or "en"))
    if mode == "app_locale":
        return normalize_reply_language(user.locale)
    return normalize_reply_language(planner_language)


def _with_reply_language(user: User, text: str, plan: AgentPlan) -> AgentPlan:
    language = _reply_language_for_turn(user, text, plan.language)
    return plan if plan.language == language else plan.model_copy(update={"language": language})


def _with_schedule_read_guard(
    user: User,
    text: str,
    plan: AgentPlan,
    *,
    allow_implicit_date: bool = False,
) -> AgentPlan:
    request = _schedule_read_request_from_text(text, user, allow_implicit=allow_implicit_date)
    if plan.tool_calls:
        if (
            request is not None
            and plan.mode == "tool_calls"
            and all(call.name == "read_calendar_events" for call in plan.tool_calls)
        ):
            return plan.model_copy(update={
                "tool_calls": [
                    call.model_copy(update={
                        "evidence": [*call.evidence, "backend_guard:schedule_read"],
                    })
                    for call in plan.tool_calls
                ]
            })
        return plan
    if plan.visual_intent != "none" or plan.needs_media_understanding:
        return plan
    if plan.mode not in {"final_answer", "ask_user"}:
        return plan
    if request is None:
        return plan
    return plan.model_copy(update={
        "mode": "tool_calls",
        "tool_calls": [
            PlannedToolCall(
                name="read_calendar_events",
                args=request.model_dump(mode="json"),
                confidence=0.9,
                requires_confirmation=False,
                evidence=["backend_guard:schedule_read"],
            )
        ],
        "final_answer": None,
        "should_answer_normally": False,
        "user_visible_status": _text_for_language(
            plan.language,
            en="Checking your calendar...",
            ru="Смотрю календарь...",
            it="Controllo il calendario...",
        ),
        "progress_kind": "reading_calendar",
    })


def _is_schedule_read_guard_plan(plan: AgentPlan) -> bool:
    return any(
        call.name == "read_calendar_events" and "backend_guard:schedule_read" in call.evidence
        for call in plan.tool_calls
    )


def _is_user_visible_schedule_read_plan(plan: AgentPlan, text: str, user: User) -> bool:
    return (
        plan.mode == "tool_calls"
        and bool(plan.tool_calls)
        and all(call.name == "read_calendar_events" for call in plan.tool_calls)
        and (_is_schedule_read_guard_plan(plan) or _schedule_read_request_from_text(text, user) is not None)
    )


def _schedule_read_request_from_text(
    text: str,
    user: User,
    *,
    allow_implicit: bool = False,
) -> CalendarEventsRequest | None:
    lowered = text.lower()
    if not lowered.strip():
        return None
    if _matches_any(lowered, SCHEDULE_MUTATION_KEYWORDS):
        return None
    has_schedule_keyword = _matches_any(lowered, SCHEDULE_READ_KEYWORDS)
    if not has_schedule_keyword and not allow_implicit:
        return None

    today = local_now(user.timezone).date()
    if _matches_any(lowered, (r"\bweek\b", r"недел")):
        start_day = today
        end_day = today + timedelta(days=7)
    else:
        day = None
        if _matches_any(lowered, (r"\btomorrow\b", r"завтра")):
            day = today + timedelta(days=1)
        elif _matches_any(lowered, (r"\btoday\b", r"сегодня")):
            day = today
        else:
            weekday = _requested_weekday(lowered)
            if weekday is not None:
                days_until = (weekday - today.weekday()) % 7
                if days_until == 0 or _matches_any(lowered, (r"\bnext\b", r"следующ")):
                    days_until = days_until or 7
                day = today + timedelta(days=days_until)
        if day is None:
            return None
        start_day = day
        end_day = day + timedelta(days=1)

    if not (_matches_any(lowered, SCHEDULE_DATE_REF_KEYWORDS) or _requested_weekday(lowered) is not None):
        return None

    return CalendarEventsRequest(
        start_at_local=datetime.combine(start_day, time.min),
        end_at_local=datetime.combine(end_day, time.min),
        include_details=True,
        sync_if_needed=True,
    )


def _requested_weekday(text: str) -> int | None:
    for weekday, patterns in WEEKDAY_ALIASES.items():
        if _matches_any(text, patterns):
            return weekday
    return None


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _text_has_schedule_read_context(text: str) -> bool:
    return _matches_any(text.lower(), SCHEDULE_CONTEXT_KEYWORDS)


def _safe_action_failure_reply(language: str | None, reason: str) -> str:
    if reason == "low_confidence":
        return "Did not perform the action: planner confidence was too low."
    if reason == "tool_call_limit":
        return "I stopped because the planning budget was reached. Please rephrase or narrow the request."
    return "Did not perform the action: planner did not return a backend tool."


def _safe_no_answer_reply(language: str | None) -> str:
    return "I could not choose a safe response. Please rephrase."


def _safe_user_visible_status(status: str | None, *, language: str | None = None) -> str:
    if status is None:
        return NEUTRAL_PROGRESS_STATUS
    text = " ".join(str(status).split()).strip()
    if not text or len(text) > 80:
        return NEUTRAL_PROGRESS_STATUS
    lower = text.lower()
    if any(marker in lower for marker in ("http://", "https://", "www.")):
        return NEUTRAL_PROGRESS_STATUS
    if any(marker in text for marker in ("[", "](", "<", ">")):
        return NEUTRAL_PROGRESS_STATUS
    if (language or "").split("-", 1)[0].lower() in {"en", "it", "es", "de", "fr", "pt"}:
        if any("а" <= char.lower() <= "я" or char.lower() == "ё" for char in text):
            return NEUTRAL_PROGRESS_STATUS
    done_claims = (
        "done",
        "created",
        "added",
        "completed",
        "готов",
        "создал",
        "создала",
        "создан",
        "добавил",
        "добавила",
        "aggiunto",
        "creato",
        "fatto",
        "completato",
    )
    if any(marker in lower for marker in done_claims):
        return NEUTRAL_PROGRESS_STATUS
    return text


def _looks_like_multi_step_request(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in MULTI_STEP_INTENT_MARKERS)


def _looks_like_flexible_calendar_slot_request(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in FLEXIBLE_CALENDAR_SLOT_MARKERS)


def _calendar_busy_intervals(events) -> list[tuple]:
    return [
        (event.start_at, event.end_at)
        for event in events
        if event.busy and event.status in (
            CalendarEventStatus.CONFIRMED,
            CalendarEventStatus.TENTATIVE,
            CalendarEventStatus.PROPOSED,
        )
    ]


def _text_for_language(language: str | None, *, en: str, ru: str, it: str | None = None) -> str:
    primary = normalize_reply_language(language)
    if primary == "ru":
        return ru
    if primary == "it":
        return it or en
    return en


def _accept_block_button_text(language: str | None) -> str:
    return _text_for_language(
        language,
        en="✓ Accept block",
        ru="✓ Принять блок",
        it="✓ Accetta blocco",
    )


def _calendar_conflict_text(
    language: str | None,
    *,
    title: str,
    conflict_title: str,
    start_label: str,
    end_label: str,
) -> str:
    return _text_for_language(
        language,
        en=(
            f"Could not create “{title}”: {start_label}–{end_label} overlaps "
            f"with “{conflict_title}”."
        ),
        ru=(
            f"Не создал «{title}»: {start_label}–{end_label} пересекается "
            f"с «{conflict_title}»."
        ),
        it=(
            f"Non ho creato “{title}”: {start_label}–{end_label} si sovrappone "
            f"a “{conflict_title}”."
        ),
    )


def _calendar_added_text(language: str | None, *, title: str, start_label: str) -> str:
    return _text_for_language(
        language,
        en=f"Added to calendar: {title} {start_label}",
        ru=f"Добавил в календарь: {title} {start_label}",
        it=f"Aggiunto al calendario: {title} {start_label}",
    )


def _calendar_proposed_text(language: str | None, *, title: str, start_label: str) -> str:
    return _text_for_language(
        language,
        en=f"Proposed block “{title}” {start_label} — confirmation required",
        ru=f"Предложил блок «{title}» {start_label} — нужно подтверждение",
        it=f"Ho proposto il blocco “{title}” {start_label} — serve conferma",
    )


def _calendar_more_text(language: str | None, count: int) -> str:
    return _text_for_language(
        language,
        en=f"+ {count} more in calendar",
        ru=f"+ ещё {count} в календаре",
        it=f"+ altri {count} nel calendario",
    )


def _calendar_empty_text(language: str | None, *, sync_error: bool) -> str:
    if sync_error:
        return _text_for_language(
            language,
            en="I did not find calendar events in that window. External sync is unavailable right now.",
            ru="Не нашёл событий в календаре за этот период. Внешняя синхронизация сейчас недоступна.",
            it="Non ho trovato eventi in quel periodo. La sincronizzazione esterna ora non e disponibile.",
        )
    return _text_for_language(
        language,
        en="I did not find calendar events in that window.",
        ru="Не нашёл событий в календаре за этот период.",
        it="Non ho trovato eventi in quel periodo.",
    )


def _calendar_window_title(language: str | None, *, start: datetime, end: datetime, tz: str) -> str:
    start_local = utc_to_local(start, tz)
    end_local = utc_to_local(end - timedelta(seconds=1), tz) if end > start else start_local
    same_day = start_local.date() == end_local.date()
    title = schedule_window_title(language=language, start=start, end=end, timezone=tz)
    if same_day and utc_to_local(utc_now(), tz).date() == start_local.date():
        label = title.removeprefix("📅 ").strip()
        return _text_for_language(
            language,
            en=f"📅 Today, {label}",
            ru=f"📅 Сегодня, {label}",
            it=f"📅 Oggi, {label}",
        )
    return title


def _calendar_event_when(event, tz: str) -> str:
    if event.all_day:
        return "all day"
    start_local = utc_to_local(event.start_at, tz)
    end_local = utc_to_local(event.end_at, tz)
    return f"{start_local.strftime('%H:%M')}–{end_local.strftime('%H:%M')}"


def _calendar_event_start_label(
    event,
    tz: str,
    *,
    include_date: bool,
    language: str | None,
) -> str:
    if event.all_day:
        return _text_for_language(
            language,
            en="all day",
            ru="весь день",
            it="tutto il giorno",
        )
    start_local = utc_to_local(event.start_at, tz)
    if include_date:
        return start_local.strftime("%d.%m %H:%M")
    return start_local.strftime("%H:%M")


def _calendar_duration_text(language: str | None, duration: timedelta) -> str:
    total_minutes = max(1, round(duration.total_seconds() / 60))
    hours, minutes = divmod(total_minutes, 60)
    lang = normalize_reply_language(language)
    if lang == "ru":
        if hours and minutes:
            return f"{hours}ч {minutes}м"
        if hours:
            return f"{hours}ч"
        return f"{minutes}м"
    if lang == "it":
        if hours and minutes:
            return f"{hours}h {minutes}m"
        if hours:
            return f"{hours}h"
        return f"{minutes} min"
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def _calendar_free_label(language: str | None) -> str:
    return _text_for_language(language, en="Free", ru="Свободно", it="Libero")


def _calendar_timeline_reply(
    *,
    events: list[Any],
    language: str | None,
    start: datetime,
    end: datetime,
    tz: str,
    include_details: bool,
) -> tuple[list[str], list[str]]:
    start_date = utc_to_local(start, tz).date()
    end_date = (
        utc_to_local(end - timedelta(seconds=1), tz).date()
        if end > start
        else start_date
    )
    include_date = start_date != end_date
    reply_lines = [_calendar_window_title(language, start=start, end=end, tz=tz)]
    rich_lines = [f"<b>{escape(reply_lines[0])}</b>"]
    visible_events = events[:CALENDAR_TELEGRAM_EVENT_LIMIT]
    busy_cursor: datetime | None = None

    for event in visible_events:
        if busy_cursor is not None and event.start_at > busy_cursor:
            gap = event.start_at - busy_cursor
            if gap >= timedelta(minutes=CALENDAR_TELEGRAM_FREE_GAP_MINUTES):
                gap_start = utc_to_local(busy_cursor, tz)
                free_line = (
                    f"⬜ {gap_start.strftime('%H:%M')}  "
                    f"{_calendar_free_label(language)} · {_calendar_duration_text(language, gap)}"
                )
                reply_lines.append(free_line)
                rich_lines.append(escape(free_line))

        start_label = _calendar_event_start_label(
            event,
            tz,
            include_date=include_date,
            language=language,
        )
        duration = _calendar_duration_text(language, event.end_at - event.start_at)
        title = truncate(event.title, 64)
        reply_line = f"🟦 {start_label}  {title} · {duration}"
        reply_lines.append(reply_line)

        rich_item = f"<b>🟦 {escape(start_label)}</b>  {escape(title)} · {escape(duration)}"
        meeting_url = event.metadata_.get("meeting_url")
        if include_details and meeting_url:
            rich_item += f'  <a href="{escape(str(meeting_url), quote=True)}">↗</a>'
        rich_lines.append(rich_item)

        busy_cursor = max(busy_cursor or event.end_at, event.end_at)

    return reply_lines, rich_lines


def _mini_app_button_text(language: str | None) -> str:
    return _text_for_language(
        language,
        en="✨ Open Lumi",
        ru="✨ Открыть Lumi",
        it="✨ Apri Lumi",
    )


def _tool_observation(
    call: PlannedToolCall,
    *,
    status: str,
    summaries: list[str],
) -> dict[str, Any]:
    summary = " ".join(" ".join(item.split()) for item in summaries if item).strip()
    next_valid_actions = ["final_answer"]
    if call.name == "read_calendar_events":
        next_valid_actions = [
            "create_internal_calendar_block",
            "create_external_calendar_event",
            "read_calendar_events",
            "final_answer",
            "ask_user",
        ]
    elif call.name == "read_tasks":
        next_valid_actions = [
            "update_task",
            "bulk_update_tasks",
            "create_task",
            "read_tasks",
            "final_answer",
            "ask_user",
        ]
    return {
        "tool": call.name,
        "status": status,
        "summary": truncate(summary, 1200),
        "next_valid_actions": next_valid_actions,
    }


def _store_planner_trace(
    run,
    trace: dict[str, Any] | None,
    *,
    stage: str,
    planner_context: PlannerContext | None = None,
) -> None:
    if not trace:
        return
    item = {"stage": stage, **trace}
    if planner_context is not None:
        item["planner_context"] = planner_context.to_trace_summary()
    existing = list((run.metadata_ or {}).get("planner_traces") or [])
    existing.append(item)
    run.metadata_ = {
        **(run.metadata_ or {}),
        "planner_trace": item,
        "planner_traces": existing[-5:],
    }


class AssistantOrchestrator:
    def __init__(self, session: AsyncSession, *, llm: LLMGateway | None = None) -> None:
        self.session = session
        self.llm = llm or LLMGateway()
        self.users = UserService(session)
        self.tasks = TaskService(session)
        self.memory = MemoryService(session)
        self.calendar = CalendarService(session)
        self.confirmations = ConfirmationService(session)
        self.runs = RunService(session)
        self.planner = AgentPlanner(self.llm)
        self.media_understanding = MediaUnderstandingService(self.llm)
        self.media_reference = MediaReferenceService(self.llm)
        self.focused_vision = FocusedVisionService(self.llm)
        self.action_reply_renderer = ActionReplyRenderer(self.llm)
        self.context_builder = ContextBuilder(session)
        self.planner_context_builder = PlannerContextBuilder(session)
        self.planning = PlanningService(session, llm=self.llm)

    async def handle_user_message(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        telegram_message_id: int | None,
        text: str,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        image: ImageInput | None = None,
        ignored_attachments: list[dict] | None = None,
        image_loader: ImageLoader | None = None,
        on_progress=None,
        on_reply_delta=None,
        touch_last_seen: bool = True,
    ) -> AssistantResult:
        async def progress(stage: str) -> None:
            if on_progress is None:
                return
            try:
                await on_progress(stage)
            except Exception:  # noqa: BLE001 — progress UI must never break the pipeline
                pass
        # 1. User / conversation
        user = await self.users.ensure_user(
            telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            touch_last_seen=touch_last_seen,
        )
        conversation = await self.users.ensure_main_conversation(user)
        image_metadata = [image.to_metadata()] if image else []
        ignored_attachment_metadata = list(ignored_attachments or [])
        stored_text = text.strip() or ("[image]" if image else "")
        final_text = text.strip() or ("Describe the image and answer the user question." if image else "")

        content_json = None
        metadata: dict = {}
        if image_metadata or ignored_attachment_metadata:
            content_json = {"text": text}
            if image_metadata:
                content_json["images"] = image_metadata
                metadata["images"] = image_metadata
            if ignored_attachment_metadata:
                content_json["ignored_attachments"] = ignored_attachment_metadata
                metadata["ignored_attachments"] = ignored_attachment_metadata

        # 2. Save inbound message
        inbound = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.USER,
            content=stored_text,
            content_json=content_json,
            char_count=len(stored_text),
            telegram_message_id=telegram_message_id,
            telegram_chat_id=telegram_chat_id,
            metadata_=metadata,
        )
        self.session.add(inbound)
        await self.session.flush()

        # 3. Agent run
        run = await self.runs.create(
            user_id=user.id,
            type_=AgentRunType.CHAT,
            trigger="telegram_message",
            conversation_id=conversation.id,
            source_message_id=inbound.id,
            input_summary=stored_text[:300],
        )
        await self.runs.mark_running(run)
        agent_run_id_var.set(str(run.id))

        # 4. Image understanding must happen before planner/final-answer short-circuits.
        media_context: MediaUnderstanding | None = None
        current_media: MediaCandidate | None = None
        selected_image = image
        if image:
            await progress("👁️ Inspecting image…")
            media_context = await self.media_understanding.analyze(
                user_id=user.id,
                timezone=user.timezone,
                text=text,
                image=image,
                agent_run_id=run.id,
                session=self.session,
            )
            media_json = media_context.to_audit_json()
            inbound.content_json = {
                **(inbound.content_json or {"text": text}),
                "images": image_metadata,
                "media_context": media_json,
            }
            inbound.metadata_ = {
                **(inbound.metadata_ or {}),
                "images": image_metadata,
                "media_context": media_json,
            }
            current_media = MediaCandidate(
                id=media_candidate_id(image.source, image_metadata[0]),
                source=image.source,
                metadata=image_metadata[0],
                media_context=media_context,
                image=image,
            )

        recent_media = []
        if not ignored_attachment_metadata:
            recent_media = await self._recent_media_candidates(
                conversation.id,
                exclude_message_id=inbound.id,
            )
        available_media = _dedupe_media_candidates(
            ([current_media] if current_media is not None else []) + recent_media
        )

        # 5. Planner call (separate small call — reliable and predictable;
        # a combined signals+reply call made M3 reason for minutes, parked for now)
        planner_context = await self.planner_context_builder.build(
            user=user,
            conversation=conversation,
        )
        schedule_followup_context = await self._recent_schedule_read_context(
            conversation_id=conversation.id,
            exclude_message_id=inbound.id,
        )
        plan = await self.planner.plan(
            user=user,
            text=text,
            known_context=planner_context.to_prompt_text(),
            media_context=media_context,
            available_media=available_media,
            agent_run_id=run.id,
            session=self.session,
        )
        _store_planner_trace(
            run,
            self.planner.last_trace,
            stage="initial",
            planner_context=planner_context,
        )
        plan = _with_reply_language(user, text, plan)
        plan = _with_schedule_read_guard(
            user,
            text,
            plan,
            allow_implicit_date=schedule_followup_context,
        )
        selected_media = _selected_or_current_media(plan, available_media, current_media)
        focused_question_override: str | None = None
        if selected_media is None and available_media and text.strip():
            media_reference = await self.media_reference.resolve(
                user_id=user.id,
                timezone=user.timezone,
                text=text,
                available_media=available_media,
                agent_run_id=run.id,
                session=self.session,
            )
            if media_reference.references_media:
                referenced_media = _find_media_candidate(media_reference.media_id, available_media)
                if referenced_media is not None:
                    selected_media = referenced_media
                    focused_question_override = media_reference.question
                    if plan.visual_intent == "none" and media_reference.visual_intent != "none":
                        plan = plan.model_copy(update={"visual_intent": media_reference.visual_intent})

        if selected_media is not None:
            selected_image = selected_media.image
            media_context = selected_media.media_context or media_context
            self._store_selected_media_audit(inbound, text, selected_media, media_context)

        if plan.mode == "needs_media_understanding" or plan.needs_media_understanding:
            if selected_media is None:
                reply_text = MEDIA_REQUIRED_REPLY
                outbound = Message(
                    conversation_id=conversation.id,
                    user_id=user.id,
                    role=MessageRole.ASSISTANT,
                    content=reply_text,
                    char_count=len(reply_text),
                    telegram_chat_id=telegram_chat_id,
                )
                self.session.add(outbound)
                await self.runs.mark_completed(run, result_summary="media_required")
                needs_compaction = await self._needs_compaction(conversation)
                return _reply_result(reply_text, run_id=run.id, needs_compaction=needs_compaction)

            selected_image = await self._ensure_candidate_image(selected_media, image_loader)
            if selected_image is None:
                reply_text = MEDIA_REQUIRED_REPLY
                outbound = Message(
                    conversation_id=conversation.id,
                    user_id=user.id,
                    role=MessageRole.ASSISTANT,
                    content=reply_text,
                    char_count=len(reply_text),
                    telegram_chat_id=telegram_chat_id,
                )
                self.session.add(outbound)
                await self.runs.mark_completed(run, result_summary="media_load_failed")
                needs_compaction = await self._needs_compaction(conversation)
                return _reply_result(reply_text, run_id=run.id, needs_compaction=needs_compaction)

            await progress("👁️ Inspecting image…")
            media_context = await self.media_understanding.analyze(
                user_id=user.id,
                timezone=user.timezone,
                text=text,
                image=selected_image,
                agent_run_id=run.id,
                session=self.session,
            )
            selected_media.media_context = media_context
            self._store_selected_media_audit(inbound, text, selected_media, media_context)
            plan = await self.planner.plan(
                user=user,
                text=text,
                known_context=planner_context.to_prompt_text(),
                media_context=media_context,
                available_media=available_media,
                agent_run_id=run.id,
                session=self.session,
            )
            _store_planner_trace(
                run,
                self.planner.last_trace,
                stage="after_media_understanding",
                planner_context=planner_context,
            )
            plan = _with_reply_language(user, text, plan)
            plan = _with_schedule_read_guard(
                user,
                text,
                plan,
                allow_implicit_date=schedule_followup_context,
            )
            selected_media = _selected_or_current_media(plan, available_media, selected_media)
            if selected_media is not None:
                selected_image = selected_media.image or selected_image
                media_context = selected_media.media_context or media_context
                self._store_selected_media_audit(inbound, text, selected_media, media_context)

        if image and not text.strip() and plan.tool_calls:
            log.warning(
                "suppressing image-only planner tool calls",
                fields={"tool_names": [call.name for call in plan.tool_calls]},
            )
            plan = plan.model_copy(update={
                "mode": "final_answer",
                "tool_calls": [],
                "should_answer_normally": True,
            })

        if plan.visual_intent == "read_only" and plan.tool_calls:
            log.warning(
                "suppressing read-only visual planner tool calls",
                fields={"tool_names": [call.name for call in plan.tool_calls]},
            )
            plan = plan.model_copy(update={
                "mode": "final_answer" if plan.final_answer else plan.mode,
                "tool_calls": [],
                "should_answer_normally": True,
            })

        policy_violations = _image_write_policy_violations(plan)
        if policy_violations:
            log.warning(
                "suppressing image-sourced write calls without action_evidence intent",
                fields={"tool_names": [call.name for call in policy_violations]},
            )
            remaining_calls = [call for call in plan.tool_calls if call not in policy_violations]
            plan = plan.model_copy(update={"tool_calls": remaining_calls})
            if not remaining_calls:
                if plan.tool_calls:
                    plan = plan.model_copy(update={"tool_calls": []})
                reply_text = plan.final_answer or (
                    "I will not perform image-based actions without an explicit user command."
                )
                outbound = Message(
                    conversation_id=conversation.id,
                    user_id=user.id,
                    role=MessageRole.ASSISTANT,
                    content=reply_text,
                    char_count=len(reply_text),
                    telegram_chat_id=telegram_chat_id,
                )
                self.session.add(outbound)
                await self.runs.mark_completed(run, result_summary=reply_text[:2000])
                needs_compaction = await self._needs_compaction(conversation)
                return _reply_result(reply_text, run_id=run.id, needs_compaction=needs_compaction)

        if (
            selected_media is not None
            and media_context is not None
            and not plan.tool_calls
            and not plan.final_answer
            and plan.visual_intent != "action_evidence"
            and plan.mode not in ("needs_media_understanding", "needs_focused_vision")
            and (text.strip() or plan.visual_intent == "read_only")
        ):
            question = (
                focused_question_override
                or text.strip()
                or "Describe the image and answer the read-only visual request."
            )
            plan = plan.model_copy(update={
                "mode": "needs_focused_vision",
                "focused_vision": FocusedVisionRequest(
                    question=question,
                    reason="planner selected media but did not provide a read-only answer",
                    confidence=0.5,
                ),
                "should_answer_normally": False,
            })

        if (
            selected_media is not None
            and media_context is not None
            and not text.strip()
            and not plan.tool_calls
        ):
            reply_text = media_context.summary or plan.final_answer or "I could not confidently describe the image."
            outbound = Message(
                conversation_id=conversation.id,
                user_id=user.id,
                role=MessageRole.ASSISTANT,
                content=reply_text,
                char_count=len(reply_text),
                telegram_chat_id=telegram_chat_id,
            )
            self.session.add(outbound)
            await self.runs.mark_completed(run, result_summary=reply_text[:2000])
            needs_compaction = await self._needs_compaction(conversation)
            return AssistantResult(
                reply_text=reply_text,
                agent_run_id=run.id,
                needs_compaction=needs_compaction,
            )

        if plan.mode == "needs_focused_vision":
            if selected_media is not None and selected_image is None:
                selected_image = await self._ensure_candidate_image(selected_media, image_loader)
            if selected_media is not None and media_context is None and selected_image is not None:
                await progress("👁️ Inspecting image…")
                media_context = await self.media_understanding.analyze(
                    user_id=user.id,
                    timezone=user.timezone,
                    text=text,
                    image=selected_image,
                    agent_run_id=run.id,
                    session=self.session,
                )
                selected_media.media_context = media_context
                self._store_selected_media_audit(inbound, text, selected_media, media_context)

            if selected_image is None or media_context is None or plan.tool_calls or plan.focused_vision is None:
                reply_text = FOCUSED_VISION_UNSAFE_REPLY
                outbound = Message(
                    conversation_id=conversation.id,
                    user_id=user.id,
                    role=MessageRole.ASSISTANT,
                    content=reply_text,
                    char_count=len(reply_text),
                    telegram_chat_id=telegram_chat_id,
                )
                self.session.add(outbound)
                await self.runs.mark_completed(run, result_summary="focused_vision_rejected")
                needs_compaction = await self._needs_compaction(conversation)
                return AssistantResult(
                    reply_text=reply_text,
                    agent_run_id=run.id,
                    needs_compaction=needs_compaction,
                )

            await progress("🔎 Checking image detail…")
            focused_result = await self.focused_vision.analyze(
                user_id=user.id,
                timezone=user.timezone,
                text=text,
                question=plan.focused_vision.question,
                image=selected_image,
                media_context=media_context,
                agent_run_id=run.id,
                session=self.session,
            )
            focused_json = {
                "request": plan.focused_vision.model_dump(mode="json"),
                "result": focused_result.to_audit_json(),
            }
            inbound.content_json = {
                **(inbound.content_json or {"text": text}),
                "focused_vision": focused_json,
            }
            inbound.metadata_ = {
                **(inbound.metadata_ or {}),
                "focused_vision": focused_json,
            }
            reply_text = focused_result.answer or (
                "I could not confidently inspect that image detail."
            )
            outbound = Message(
                conversation_id=conversation.id,
                user_id=user.id,
                role=MessageRole.ASSISTANT,
                content=reply_text,
                char_count=len(reply_text),
                telegram_chat_id=telegram_chat_id,
            )
            self.session.add(outbound)
            await self.runs.mark_completed(run, result_summary=reply_text[:2000])
            needs_compaction = await self._needs_compaction(conversation)
            return AssistantResult(
                reply_text=reply_text,
                agent_run_id=run.id,
                needs_compaction=needs_compaction,
            )

        # 6. Apply safe actions through the bounded planner loop.
        loop_result = await self._run_tool_loop(
            user=user,
            run=run,
            plan=plan,
            text=text,
            source_message_id=inbound.id,
            planner_context=planner_context,
            media_context=media_context,
            available_media=available_media,
            progress=progress,
        )
        plan = loop_result.plan
        action_results = loop_result.action_results
        action_outcomes = loop_result.action_outcomes
        buttons = loop_result.buttons
        reply_rich_html = loop_result.reply_rich_html
        open_app_button = loop_result.open_app_button
        open_app_button_label = _mini_app_button_text(plan.language) if open_app_button else None

        if not action_results and plan.mode == "tool_calls":
            reason = (
                "tool_call_limit"
                if loop_result.stop_reason in {"step_limit_reached", "tool_call_limit_reached"}
                else "missing_tool"
            )
            reply_text = _safe_action_failure_reply(plan.language, reason)
            outbound = Message(
                conversation_id=conversation.id,
                user_id=user.id,
                role=MessageRole.ASSISTANT,
                content=reply_text,
                char_count=len(reply_text),
                telegram_chat_id=telegram_chat_id,
            )
            self.session.add(outbound)
            await self.runs.mark_completed(run, result_summary="planner_no_backend_tool")
            needs_compaction = await self._needs_compaction(conversation)
            return AssistantResult(
                reply_text=reply_text,
                buttons=buttons,
                agent_run_id=run.id,
                needs_compaction=needs_compaction,
                open_app_button=open_app_button,
                open_app_button_label=open_app_button_label,
            )

        if action_results and loop_result.stop_reason in {"step_limit_reached", "tool_call_limit_reached"}:
            reply_text = (
                "I stopped because the planning budget was reached.\n\n"
                + "\n".join(f"• {result}" for result in action_results[-3:])
            )
            outbound = Message(
                conversation_id=conversation.id,
                user_id=user.id,
                role=MessageRole.ASSISTANT,
                content=reply_text,
                char_count=len(reply_text),
                telegram_chat_id=telegram_chat_id,
            )
            self.session.add(outbound)
            await self.runs.mark_completed(run, result_summary=loop_result.stop_reason)
            needs_compaction = await self._needs_compaction(conversation)
            return AssistantResult(
                reply_text=reply_text,
                buttons=buttons,
                agent_run_id=run.id,
                needs_compaction=needs_compaction,
            )

        if action_results and not plan.should_answer_normally:
            rendered_reply = None
            if loop_result.use_action_reply_renderer:
                rendered_reply = await self.action_reply_renderer.render(
                    user=user,
                    latest_user_message=text,
                    planner_language=plan.language,
                    outcomes=action_outcomes,
                    run_id=run.id,
                    session=self.session,
                )
            if rendered_reply is not None:
                reply_text = rendered_reply.message
                buttons = self._with_rendered_button_labels(
                    buttons,
                    rendered_reply.button_labels,
                )
            else:
                reply_text = self._format_action_results_reply(action_results)
            outbound = Message(
                conversation_id=conversation.id,
                user_id=user.id,
                role=MessageRole.ASSISTANT,
                content=reply_text,
                char_count=len(reply_text),
                telegram_chat_id=telegram_chat_id,
            )
            self.session.add(outbound)
            await self.runs.mark_completed(run, result_summary="; ".join(action_results))
            needs_compaction = await self._needs_compaction(conversation)
            return AssistantResult(
                reply_text=reply_text,
                buttons=buttons,
                agent_run_id=run.id,
                needs_compaction=needs_compaction,
                open_app_button=open_app_button,
                open_app_button_label=open_app_button_label,
                reply_rich_html=reply_rich_html if len(action_results) == 1 else None,
            )

        if not action_results and plan.mode in ("final_answer", "ask_user") and plan.final_answer:
            reply_text = plan.final_answer
            outbound = Message(
                conversation_id=conversation.id,
                user_id=user.id,
                role=MessageRole.ASSISTANT,
                content=reply_text,
                char_count=len(reply_text),
                telegram_chat_id=telegram_chat_id,
            )
            self.session.add(outbound)
            await self.runs.mark_completed(run, result_summary=reply_text[:2000])
            needs_compaction = await self._needs_compaction(conversation)
            return AssistantResult(
                reply_text=reply_text,
                buttons=buttons,
                agent_run_id=run.id,
                needs_compaction=needs_compaction,
                open_app_button=open_app_button,
                open_app_button_label=open_app_button_label,
            )

        if not action_results and not plan.final_answer:
            reply_text = _safe_no_answer_reply(plan.language)
            outbound = Message(
                conversation_id=conversation.id,
                user_id=user.id,
                role=MessageRole.ASSISTANT,
                content=reply_text,
                char_count=len(reply_text),
                telegram_chat_id=telegram_chat_id,
            )
            self.session.add(outbound)
            await self.runs.mark_completed(run, result_summary="planner_no_final_answer")
            needs_compaction = await self._needs_compaction(conversation)
            return AssistantResult(
                reply_text=reply_text,
                buttons=buttons,
                agent_run_id=run.id,
                needs_compaction=needs_compaction,
            )

        # 6-7. Final reply
        await progress(
            "✍️ Writing reply…" if not action_results
            else "✍️ Action done. Writing reply…"
        )
        try:
            context = await self.context_builder.build(
                user=user,
                conversation=conversation,
                current_text=final_text,
                media_context=media_context,
                action_results=action_results,
            )
            if on_reply_delta is not None:
                response = await self.llm.complete_stream(
                    messages=context.messages,
                    system=context.system_prompt,
                    temperature=0.3,
                    max_tokens=2048,
                    request_kind="final_chat",
                    user_id=user.id,
                    agent_run_id=run.id,
                    session=self.session,
                    on_delta=on_reply_delta,
                    on_thinking=(lambda: progress("__thinking__")),
                )
            else:
                response = await self.llm.complete(
                    messages=context.messages,
                    system=context.system_prompt,
                    temperature=0.3,
                    max_tokens=2048,
                    request_kind="final_chat",
                    user_id=user.id,
                    agent_run_id=run.id,
                    session=self.session,
                )
            reply_text = response.text.strip() or FALLBACK_REPLY
            run.metadata_ = {**run.metadata_, "context_snapshot": context.debug_snapshot}
        except Exception as exc:  # noqa: BLE001 — chat must answer something
            log.exception("final LLM reply failed")
            await self.runs.mark_failed(run, f"final_chat: {exc}")
            if action_results:
                done = "\n".join(f"• {r}" for r in action_results)
                reply_text = f"Done:\n{done}\n\nThe model is unavailable, so I could not write a richer reply."
            else:
                reply_text = FALLBACK_REPLY
            if reply_rich_html and len(action_results) == 1:
                reply_text = action_results[0]
            outbound = Message(
                conversation_id=conversation.id,
                user_id=user.id,
                role=MessageRole.ASSISTANT,
                content=reply_text,
                char_count=len(reply_text),
            )
            self.session.add(outbound)
            return AssistantResult(
                reply_text=reply_text,
                buttons=buttons,
                agent_run_id=run.id,
                open_app_button=open_app_button,
                open_app_button_label=open_app_button_label,
                reply_rich_html=reply_rich_html if len(action_results) == 1 else None,
            )

        # 8. Save assistant message
        if reply_rich_html and len(action_results) == 1:
            reply_text = action_results[0]
        outbound = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.ASSISTANT,
            content=reply_text,
            char_count=len(reply_text),
            telegram_chat_id=telegram_chat_id,
        )
        self.session.add(outbound)

        await self.runs.mark_completed(
            run, result_summary="; ".join(action_results) if action_results else "chat reply"
        )

        # 9. Compaction check
        needs_compaction = await self._needs_compaction(conversation)

        return AssistantResult(
            reply_text=reply_text,
            buttons=buttons,
            agent_run_id=run.id,
            needs_compaction=needs_compaction,
            open_app_button=open_app_button,
            open_app_button_label=open_app_button_label,
            reply_rich_html=reply_rich_html if len(action_results) == 1 else None,
        )

    # ------------------------------------------------------------------

    async def _recent_media_candidates(
        self,
        conversation_id: uuid.UUID,
        *,
        exclude_message_id: uuid.UUID,
        limit: int = 3,
    ) -> list[MediaCandidate]:
        result = await self.session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == MessageRole.USER,
                Message.id != exclude_message_id,
                Message.metadata_["images"].is_not(None),
            )
            .order_by(Message.created_at.desc())
            .limit(50)
        )
        candidates: list[MediaCandidate] = []
        for message in result.scalars():
            metadata = message.metadata_ or {}
            media_context = _media_context_from_payload(
                metadata.get("media_context") or (message.content_json or {}).get("media_context")
            )
            for image_metadata in metadata.get("images") or []:
                image_metadata = dict(image_metadata)
                candidates.append(MediaCandidate(
                    id=media_candidate_id("recent", image_metadata),
                    source="recent",
                    metadata=image_metadata,
                    media_context=media_context,
                ))
                if len(candidates) >= limit:
                    return candidates
        return candidates

    async def _recent_schedule_read_context(
        self,
        conversation_id: uuid.UUID,
        *,
        exclude_message_id: uuid.UUID,
    ) -> bool:
        result = await self.session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.id != exclude_message_id,
                Message.role.in_([MessageRole.USER, MessageRole.ASSISTANT]),
            )
            .order_by(Message.created_at.desc())
            .limit(6)
        )
        return any(_text_has_schedule_read_context(message.content or "") for message in result.scalars())

    async def _ensure_candidate_image(
        self,
        candidate: MediaCandidate,
        image_loader: ImageLoader | None,
    ) -> ImageInput | None:
        if candidate.image is not None:
            return candidate.image
        if image_loader is None:
            return None
        try:
            candidate.image = await image_loader(candidate.metadata)
        except Exception as exc:  # noqa: BLE001
            log.warning("selected media download failed", fields={"media_id": candidate.id, "error": str(exc)[:300]})
            candidate.image = None
        return candidate.image

    @staticmethod
    def _store_selected_media_audit(
        inbound: Message,
        text: str,
        candidate: MediaCandidate,
        media_context: MediaUnderstanding | None,
    ) -> None:
        media_json = media_context.to_audit_json() if media_context is not None else None
        content_json = {
            **(inbound.content_json or {"text": text}),
            "referenced_images": [candidate.metadata],
        }
        metadata = {
            **(inbound.metadata_ or {}),
            "referenced_images": [candidate.metadata],
        }
        if media_json is not None:
            content_json["media_context"] = media_json
            metadata["media_context"] = media_json
        inbound.content_json = content_json
        inbound.metadata_ = metadata

    # ------------------------------------------------------------------

    @staticmethod
    def _format_action_results_reply(action_results: list[str]) -> str:
        if len(action_results) == 1:
            return action_results[0]
        return "Done:\n" + "\n".join(f"• {result}" for result in action_results)

    @staticmethod
    def _with_rendered_button_labels(
        buttons: list[list[Button]],
        labels: dict[str, str],
    ) -> list[list[Button]]:
        if not labels:
            return buttons
        rendered: list[list[Button]] = []
        for row in buttons:
            rendered_row: list[Button] = []
            for button in row:
                text = labels.get(button.key or "", button.text)
                rendered_row.append(Button(text=text, callback_data=button.callback_data, key=button.key))
            rendered.append(rendered_row)
        return rendered

    async def _needs_compaction(self, conversation) -> bool:
        from lumi.assistant.compaction import CompactionService

        return await CompactionService(self.session, llm=self.llm).needs_compaction(conversation)

    # ------------------------------------------------------------------

    async def _run_tool_loop(
        self,
        *,
        user: User,
        run,
        plan: AgentPlan,
        text: str,
        source_message_id: uuid.UUID,
        planner_context: PlannerContext,
        media_context: MediaUnderstanding | None,
        available_media: list[MediaCandidate],
        progress: Callable[[str], Awaitable[None]],
    ) -> ToolLoopResult:
        all_results: list[str] = []
        all_outcomes: list[ActionOutcome] = []
        all_buttons: list[list[Button]] = []
        observations: list[dict[str, Any]] = []
        loop_steps: list[dict[str, Any]] = []
        reply_rich_html: str | None = None
        open_app_button = False
        use_action_reply_renderer = True
        tool_call_count = 0
        stop_reason = "no_tool_calls"

        for step_index in range(AGENT_LOOP_MAX_MODEL_STEPS):
            if not plan.tool_calls:
                stop_reason = "planner_final" if plan.mode in {"final_answer", "ask_user"} else "no_tool_calls"
                break

            if tool_call_count + len(plan.tool_calls) > AGENT_LOOP_MAX_TOOL_CALLS:
                stop_reason = "tool_call_limit_reached"
                break

            await progress(_safe_user_visible_status(plan.user_visible_status, language=plan.language))
            (
                step_results,
                step_outcomes,
                step_buttons,
                step_rich_html,
                step_observations,
                step_open_app_button,
                step_use_action_reply_renderer,
            ) = await self._apply_tool_calls(
                user=user,
                run=run,
                plan=plan,
                text=text,
                source_message_id=source_message_id,
                planner_context=planner_context,
            )
            tool_call_count += len(plan.tool_calls)
            all_results.extend(step_results)
            all_outcomes.extend(step_outcomes)
            all_buttons.extend(step_buttons)
            observations.extend(step_observations)
            if step_rich_html is not None:
                reply_rich_html = step_rich_html
            open_app_button = open_app_button or step_open_app_button
            use_action_reply_renderer = use_action_reply_renderer and step_use_action_reply_renderer

            has_confirmation = bool(step_buttons) or any(
                outcome.status == "requires_confirmation" for outcome in step_outcomes
            )
            loop_steps.append({
                "step": step_index + 1,
                "tool_names": [call.name for call in plan.tool_calls],
                "tool_count": len(plan.tool_calls),
                "progress_kind": plan.progress_kind,
                "status": _safe_user_visible_status(plan.user_visible_status, language=plan.language),
                "observation_count": len(step_observations),
                "requires_confirmation": has_confirmation,
            })

            if has_confirmation:
                stop_reason = "approval_required"
                break

            should_continue = (
                plan.mode == "tool_calls"
                and all(call.name in READ_ONLY_LOOP_TOOLS for call in plan.tool_calls)
                and _looks_like_multi_step_request(text)
                and not _is_user_visible_schedule_read_plan(plan, text, user)
            )
            if not should_continue:
                stop_reason = "completed"
                break

            if step_index + 1 >= AGENT_LOOP_MAX_MODEL_STEPS:
                stop_reason = "step_limit_reached"
                break
            if tool_call_count >= AGENT_LOOP_MAX_TOOL_CALLS:
                stop_reason = "tool_call_limit_reached"
                break

            plan = await self.planner.plan(
                user=user,
                text=text,
                known_context=planner_context.to_prompt_text(),
                media_context=media_context,
                available_media=available_media,
                tool_observations=observations,
                loop_step=step_index + 2,
                remaining_steps=AGENT_LOOP_MAX_MODEL_STEPS - (step_index + 1),
                agent_run_id=run.id,
                session=self.session,
            )
            _store_planner_trace(
                run,
                self.planner.last_trace,
                stage=f"loop_step_{step_index + 2}",
                planner_context=planner_context,
            )
            plan = _with_reply_language(user, text, plan)
        else:
            stop_reason = "step_limit_reached"

        run.metadata_ = {
            **(run.metadata_ or {}),
            "loop_trace": {
                "max_model_steps": AGENT_LOOP_MAX_MODEL_STEPS,
                "max_tool_calls": AGENT_LOOP_MAX_TOOL_CALLS,
                "tool_call_count": tool_call_count,
                "stop_reason": stop_reason,
                "steps": loop_steps,
                "observations": observations[-AGENT_LOOP_MAX_TOOL_CALLS:],
            },
        }
        return ToolLoopResult(
            plan=plan,
            action_results=all_results,
            action_outcomes=all_outcomes,
            buttons=all_buttons,
            reply_rich_html=reply_rich_html,
            open_app_button=open_app_button,
            use_action_reply_renderer=use_action_reply_renderer,
            stop_reason=stop_reason,
            observations=observations,
        )

    # ------------------------------------------------------------------

    async def _apply_tool_calls(
        self,
        *,
        user: User,
        run,
        plan: AgentPlan,
        text: str,
        source_message_id: uuid.UUID,
        planner_context: PlannerContext,
    ) -> tuple[list[str], list[ActionOutcome], list[list[Button]], str | None, list[dict[str, Any]], bool, bool]:
        results: list[str] = []
        outcomes: list[ActionOutcome] = []
        buttons: list[list[Button]] = []
        observations: list[dict[str, Any]] = []
        observation_summaries: list[str] = []
        rich_html: str | None = None
        open_app_button = False
        use_action_reply_renderer = True
        read_only_context = (
            plan.mode == "tool_calls"
            and all(call.name in READ_ONLY_LOOP_TOOLS for call in plan.tool_calls)
            and _looks_like_multi_step_request(text)
            and not _is_user_visible_schedule_read_plan(plan, text, user)
        )

        for call in plan.tool_calls:
            before_result_count = len(results)
            before_outcome_count = len(outcomes)
            before_button_count = len(buttons)
            before_observation_summary_count = len(observation_summaries)
            if call.name == "create_task":
                task_signal = ExtractedTask.model_validate(_args_with_call_defaults(call))
                await self._apply_create_task_tool(
                    user=user,
                    run=run,
                    call=call,
                    task_signal=task_signal,
                    source_message_id=source_message_id,
                    planner_context=planner_context,
                    language=plan.language,
                    results=results,
                    outcomes=outcomes,
                    buttons=buttons,
                )
            elif call.name == "read_tasks":
                await self._apply_read_tasks_tool(
                    user=user,
                    run=run,
                    call=call,
                    results=results,
                )
            elif call.name == "update_task":
                patch = TaskPatchRequest.model_validate(_args_with_call_defaults(call))
                await self._apply_update_task_tool(
                    user=user,
                    run=run,
                    call=call,
                    patch=patch,
                    planner_context=planner_context,
                    language=plan.language,
                    results=results,
                    buttons=buttons,
                )
            elif call.name == "bulk_update_tasks":
                patch = BulkTaskPatchRequest.model_validate(_args_with_call_defaults(call))
                await self._apply_bulk_update_tasks_tool(
                    user=user,
                    run=run,
                    call=call,
                    patch=patch,
                    language=plan.language,
                    results=results,
                    buttons=buttons,
                )
            elif call.name == "rename_task":
                update = TaskUpdate.model_validate({
                    "operation": "rename",
                    **_args_with_call_defaults(call),
                })
                await self._apply_rename_task_tool(
                    user=user,
                    run=run,
                    call=call,
                    update=update,
                    results=results,
                    buttons=buttons,
                )
            elif call.name == "complete_task":
                await self._apply_complete_task_tool(user=user, run=run, call=call, results=results)
            elif call.name == "snooze_task":
                await self._apply_snooze_task_tool(
                    user=user, run=run, call=call, results=results, buttons=buttons
                )
            elif call.name == "store_memory":
                candidate = MemoryCandidate.model_validate(_args_with_call_defaults(call))
                await self._apply_store_memory_tool(user=user, run=run, candidate=candidate,
                                                    call=call,
                                                    source_message_id=source_message_id,
                                                    results=results)
            elif call.name in {
                "plan_day",
                "find_focus_slot",
                "create_internal_calendar_block",
                "create_external_calendar_event",
            }:
                request = _calendar_request_from_tool_call(call)
                await self._apply_calendar_request(
                    user=user, run=run, call=call, request=request, results=results,
                    buttons=buttons, outcomes=outcomes, language=plan.language, text=text
                )
            elif call.name == "read_calendar_events":
                request = CalendarEventsRequest.model_validate(_args_with_call_defaults(call))
                calendar_read = await self._apply_read_calendar_events_tool(
                    user=user,
                    run=run,
                    call=call,
                    request=request,
                    results=results,
                    language=plan.language,
                    user_visible=not read_only_context,
                )
                observation_summaries.append(calendar_read.observation_summary)
                if calendar_read.reply_rich_html is not None:
                    rich_html = calendar_read.reply_rich_html
                open_app_button = open_app_button or calendar_read.open_app_button
                if calendar_read.open_app_button:
                    use_action_reply_renderer = False
            elif call.name == "create_automation":
                automation = AutomationRequest.model_validate(_args_with_call_defaults(call))
                await self._apply_create_automation_tool(user=user, run=run,
                                                         call=call,
                                                         automation=automation,
                                                         results=results, buttons=buttons)
            elif call.name == "email_triage":
                request = EmailRequest.model_validate({"kind": "triage", **call.args})
                if request.confidence >= 0.0:
                    buttons.append([Button(text="📬 Triage email", callback_data="run:email_triage")])
            elif call.name == "news_digest":
                request = NewsRequest.model_validate({
                    "kind": "digest",
                    **call.args,
                    "confidence": call.confidence,
                })
                await self._apply_news_digest_tool(
                    user=user,
                    run=run,
                    request=request,
                    results=results,
                )
            elif call.name == "set_language":
                await self._apply_set_language_tool(
                    user=user,
                    run=run,
                    call=call,
                    language=plan.language,
                    results=results,
                    outcomes=outcomes,
                )
            new_results = results[before_result_count:]
            new_outcomes = outcomes[before_outcome_count:]
            new_buttons = buttons[before_button_count:]
            new_observation_summaries = observation_summaries[before_observation_summary_count:]
            status = "skipped"
            if new_outcomes:
                status = new_outcomes[-1].status
            elif new_buttons:
                status = "requires_confirmation"
            elif new_results:
                status = "completed"
            elif new_observation_summaries:
                status = "completed"
            observations.append(_tool_observation(
                call,
                status=status,
                summaries=new_observation_summaries or new_results,
            ))

        if results and not outcomes:
            button_keys = [
                button.key
                for row in buttons
                for button in row
                if button.key
            ]
            outcomes = [
                ActionOutcome(
                    action_type="backend_action",
                    status="completed",
                    fallback_text=result,
                    button_keys=button_keys,
                )
                for result in results
            ]
        return results, outcomes, buttons, rich_html, observations, open_app_button, use_action_reply_renderer

    async def _apply_set_language_tool(
        self,
        *,
        user: User,
        run,
        call: PlannedToolCall,
        language: str,
        results: list[str],
        outcomes: list[ActionOutcome],
    ) -> None:
        args = dict(call.args)
        updates: dict[str, str] = {}
        current_settings = ensure_language_settings(user.settings)
        app_locale_raw = args.get("app_locale") or args.get("locale")
        if app_locale_raw is not None:
            try:
                app_locale = validate_app_locale(str(app_locale_raw))
            except ValueError:
                await self.runs.log_tool_call(
                    run=run,
                    tool_name="set_language",
                    status="skipped",
                    args=args,
                    result={"reason": "unsupported_locale"},
                )
                fallback = "Unsupported app language. Use English or Russian."
                results.append(fallback)
                outcomes.append(ActionOutcome(
                    action_type="set_language",
                    status="skipped",
                    fallback_text=fallback,
                    error_code="unsupported_locale",
                ))
                return
            user.locale = app_locale
            current_settings["locale_source"] = "manual"
            updates["app_locale"] = app_locale
        mode_raw = args.get("reply_language_mode")
        if mode_raw is not None:
            mode = normalize_reply_language_mode(str(mode_raw))
            current_settings["reply_language_mode"] = mode
            updates["reply_language_mode"] = mode
        reply_language_raw = args.get("reply_language")
        if reply_language_raw is not None:
            reply_language = normalize_reply_language(str(reply_language_raw))
            current_settings["reply_language"] = reply_language
            updates["reply_language"] = reply_language
        if not updates:
            await self.runs.log_tool_call(
                run=run,
                tool_name="set_language",
                status="skipped",
                args=args,
                result={"reason": "no_language_updates"},
            )
            fallback = "I did not understand which language setting to change."
            results.append(fallback)
            outcomes.append(ActionOutcome(
                action_type="set_language",
                status="skipped",
                fallback_text=fallback,
                error_code="no_language_updates",
            ))
            return

        user.settings = current_settings
        await self.runs.log_tool_call(
            run=run,
            tool_name="set_language",
            status="completed",
            args=args,
            result={
                "locale": user.locale,
                "reply_language_mode": user.settings["reply_language_mode"],
                "reply_language": user.settings.get("reply_language"),
            },
        )
        await RealtimeEventService(self.session).emit(
            user_id=user.id,
            topics=["settings"],
            event_type="settings.updated",
            payload={},
        )
        fallback = format_language_settings_reply(
            app_locale=user.locale,
            reply_language_mode=str(user.settings.get("reply_language_mode") or "auto"),
            reply_language=str(user.settings.get("reply_language") or "en"),
            language=language,
        )
        results.append(fallback)
        outcomes.append(ActionOutcome(
            action_type="set_language",
            status="completed",
            fallback_text=fallback,
            details={
                "updates": updates,
                "app_locale": user.locale,
                "reply_language_mode": user.settings.get("reply_language_mode"),
                "reply_language": user.settings.get("reply_language"),
            },
        ))

    async def _apply_create_task_tool(
        self,
        *,
        user: User,
        run,
        call: PlannedToolCall,
        task_signal: ExtractedTask,
        source_message_id: uuid.UUID,
        planner_context: PlannerContext,
        language: str,
        results: list[str],
        outcomes: list[ActionOutcome],
        buttons: list[list[Button]],
    ) -> None:
        if task_signal.project_ref and not task_signal.project:
            project = planner_context.project_for_ref(task_signal.project_ref)
            if not project:
                args = task_signal.model_dump(mode="json")
                await self.runs.log_tool_call(
                    run=run,
                    tool_name="create_task",
                    status="skipped",
                    args=args,
                    result={"reason": "project_ref_not_found"},
                )
                fallback = "I did not understand which project to use. Please clarify the project."
                results.append(fallback)
                outcomes.append(ActionOutcome(
                    action_type="create_task",
                    status="skipped",
                    fallback_text=fallback,
                    error_code="project_ref_not_found",
                    title=task_signal.title,
                ))
                return
            task_signal = task_signal.model_copy(update={"project": project})

        if task_signal.confidence >= TASK_AUTO_CREATE_CONFIDENCE and not task_signal.requires_confirmation:
            task = await self.tasks.create_task_from_signal(
                user, task_signal, source_message_id=source_message_id, agent_run_id=run.id
            )
            await self.runs.log_tool_call(
                run=run, tool_name="create_task", status="completed",
                args=task_signal.model_dump(mode="json"),
                result={"task_id": str(task.id)},
            )
            desc = f"Created task: “{task.title}”"
            if task.project:
                desc += f" in project {task.project}"
            if task.reminder_at:
                desc += f", reminder {fmt_local(task.reminder_at, user.timezone)}"
            elif task.due_at:
                desc += f", due {fmt_local(task.due_at, user.timezone)}"
            results.append(desc)
            outcomes.append(ActionOutcome(
                action_type="create_task",
                status="completed",
                fallback_text=desc,
                title=task.title,
                project=task.project,
                due_at_local=fmt_local(task.due_at, user.timezone) if task.due_at else None,
                reminder_at_local=(
                    fmt_local(task.reminder_at, user.timezone) if task.reminder_at else None
                ),
                button_keys=["task_done", "task_snooze"],
                details={"task_id": str(task.id)},
            ))
            buttons.append([
                Button(text="✓ Done", callback_data=f"task_done:{task.id}", key="task_done"),
                Button(text="⏰ Snooze", callback_data=f"task_snooze:{task.id}:tomorrow",
                       key="task_snooze"),
            ])
        elif task_signal.confidence >= TASK_CONFIRM_CONFIDENCE:
            payload = {
                **task_signal.model_dump(mode="json"),
                **_call_source_payload(call),
            }
            confirmation = await self.confirmations.create(
                user,
                action_type="create_task",
                action_payload=payload,
                prompt=_prompt_with_evidence(f"Create task “{task_signal.title}”?", call),
            )
            await self.runs.log_tool_call(
                run=run, tool_name="create_task", status="requires_confirmation",
                args=payload,
                requires_confirmation=True, confirmation_id=confirmation.id,
            )
            suffix = f" in project {task_signal.project}" if task_signal.project else ""
            fallback = f"Proposed task “{task_signal.title}”{suffix} — waiting for confirmation"
            results.append(fallback)
            outcomes.append(ActionOutcome(
                action_type="create_task",
                status="requires_confirmation",
                fallback_text=fallback,
                title=task_signal.title,
                project=task_signal.project,
                due_at_local=task_signal.due_at_local.isoformat()
                if task_signal.due_at_local else None,
                reminder_at_local=(
                    task_signal.reminder_at_local.isoformat()
                    if task_signal.reminder_at_local else None
                ),
                button_keys=["confirm", "reject"],
                details={"confirmation_id": str(confirmation.id)},
            ))
            buttons.append([
                Button(text=f"✓ Create: {task_signal.title[:28]}",
                       callback_data=f"confirm:{confirmation.id}", key="confirm"),
                Button(text="✗ No", callback_data=f"reject:{confirmation.id}", key="reject"),
            ])
        else:
            args = task_signal.model_dump(mode="json")
            await self.runs.log_tool_call(
                run=run,
                tool_name="create_task",
                status="skipped",
                args=args,
                result={"reason": "low_confidence"},
            )
            fallback = _safe_action_failure_reply(language, "low_confidence")
            results.append(fallback)
            outcomes.append(ActionOutcome(
                action_type="create_task",
                status="skipped",
                fallback_text=fallback,
                error_code="low_confidence",
                title=task_signal.title,
            ))

    async def _apply_read_tasks_tool(
        self,
        *,
        user: User,
        run,
        call: PlannedToolCall,
        results: list[str],
    ) -> None:
        filter_ = str(call.args.get("filter") or "all")
        if filter_ not in {"all", "today", "upcoming", "inbox", "done"}:
            filter_ = "all"
        limit = int(call.args.get("limit") or 10)
        limit = max(1, min(limit, 20))
        tasks = await self.tasks.list_tasks(user, filter_=filter_, limit=limit)
        await self.runs.log_tool_call(
            run=run,
            tool_name="read_tasks",
            status="completed",
            args={"filter": filter_, "limit": limit},
            result={"count": len(tasks)},
        )
        if not tasks:
            results.append("No open tasks." if filter_ != "done" else "No completed tasks.")
            return
        lines = ["Open tasks:" if filter_ != "done" else "Completed tasks:"]
        for index, task in enumerate(tasks, start=1):
            meta: list[str] = [task.priority.value]
            if task.project:
                meta.append(task.project)
            meta.extend(f"#{tag}" for tag in (task.tags or [])[:3])
            lines.append(f"{index}. {task.title} — " + ", ".join(meta))
        results.append("\n".join(lines))

    async def _apply_update_task_tool(
        self,
        *,
        user: User,
        run,
        call: PlannedToolCall,
        patch: TaskPatchRequest,
        planner_context: PlannerContext,
        language: str,
        results: list[str],
        buttons: list[list[Button]],
    ) -> None:
        updates = patch.update_fields()
        args = {
            **patch.model_dump(mode="json"),
            "updates": updates,
            **_call_source_payload(call),
        }
        if not updates:
            await self.runs.log_tool_call(
                run=run,
                tool_name="update_task",
                status="skipped",
                args=args,
                result={"reason": "no_updates"},
            )
            results.append(format_task_update_no_updates_reply(language="en"))
            return

        candidates = await self._resolve_update_task_candidates(
            user=user,
            patch=patch,
            planner_context=planner_context,
        )
        if not candidates:
            await self.runs.log_tool_call(
                run=run,
                tool_name="update_task",
                status="skipped",
                args=args,
                result={"candidate_task_ids": []},
            )
            results.append(format_task_update_not_found_reply(
                task_query=patch.task_query,
                recency_hint=patch.recency_hint,
                language="en",
            ))
            return

        if len(candidates) > 1:
            payload = {
                "task_query": patch.task_query,
                "recency_hint": patch.recency_hint,
                "updates": updates,
                "candidate_task_ids": [str(task.id) for task in candidates],
                "agent_run_id": str(run.id),
                "language": language,
                **_call_source_payload(call),
            }
            confirmation = await self.confirmations.create(
                user,
                action_type="update_task_choice",
                action_payload=payload,
                prompt=_prompt_with_evidence(
                    format_task_update_choice_prompt(language=language),
                    call,
                ),
            )
            await self.runs.log_tool_call(
                run=run,
                tool_name="update_task",
                status="requires_confirmation",
                args=args,
                result={"candidate_task_ids": [str(task.id) for task in candidates]},
                requires_confirmation=True,
                confirmation_id=confirmation.id,
            )
            results.append(format_task_update_ambiguous_reply(language="en"))
            for index, task in enumerate(candidates[:5]):
                buttons.append([
                    Button(
                        text=_rename_choice_button_text(task),
                        callback_data=_update_choice_callback(confirmation.id, index),
                    )
                ])
            return

        task = candidates[0]
        if _image_sourced_write(call):
            payload = {
                "task_id": str(task.id),
                "updates": updates,
                "agent_run_id": str(run.id),
                "language": language,
                **_call_source_payload(call),
            }
            confirmation = await self.confirmations.create(
                user,
                action_type="update_task",
                action_payload=payload,
                prompt=_prompt_with_evidence(
                    format_task_update_confirmation_prompt(task.title, language=language),
                    call,
                ),
            )
            await self.runs.log_tool_call(
                run=run,
                tool_name="update_task",
                status="requires_confirmation",
                args=args,
                result={"task_id": str(task.id)},
                requires_confirmation=True,
                confirmation_id=confirmation.id,
            )
            results.append(f"Proposed update for “{task.title}” — confirm with the button.")
            buttons.append([
                Button(text="✓ Update", callback_data=f"confirm:{confirmation.id}", key="confirm"),
                Button(text="✗ No", callback_data=f"reject:{confirmation.id}", key="reject"),
            ])
            return

        task = await self.tasks.update_task(
            user,
            task,
            updates,
            actor="agent",
            agent_run_id=run.id,
        )
        await self.runs.log_tool_call(
            run=run,
            tool_name="update_task",
            status="completed",
            args=args,
            result={"task_id": str(task.id), "updated_fields": sorted(updates)},
        )
        results.append(format_task_update_reply(task, updates, language="en"))

    async def _apply_bulk_update_tasks_tool(
        self,
        *,
        user: User,
        run,
        call: PlannedToolCall,
        patch: BulkTaskPatchRequest,
        language: str,
        results: list[str],
        buttons: list[list[Button]],
    ) -> None:
        updates = patch.update_fields()
        args = {
            **patch.model_dump(mode="json"),
            "updates": updates,
            **_call_source_payload(call),
        }
        if not patch.has_updates():
            await self.runs.log_tool_call(
                run=run,
                tool_name="bulk_update_tasks",
                status="skipped",
                args=args,
                result={"reason": "no_updates"},
            )
            results.append(format_task_update_no_updates_reply(language="en"))
            return

        candidates = await self.tasks.find_bulk_update_candidates(
            user,
            task_query=patch.task_query,
            from_project=patch.from_project,
            from_tags=patch.from_tags,
            status=patch.status,
            limit=patch.limit,
        )
        if not candidates:
            await self.runs.log_tool_call(
                run=run,
                tool_name="bulk_update_tasks",
                status="skipped",
                args=args,
                result={"candidate_task_ids": []},
            )
            results.append("I could not find matching tasks. Please clarify the filter.")
            return

        if len(candidates) == 1 and not _image_sourced_write(call):
            task = await self.tasks.update_task_with_tag_ops(
                user,
                candidates[0],
                updates,
                tags_add=patch.tags_add,
                tags_remove=patch.tags_remove,
                actor="agent",
                agent_run_id=run.id,
            )
            await self.runs.log_tool_call(
                run=run,
                tool_name="bulk_update_tasks",
                status="completed",
                args=args,
                result={"task_ids": [str(task.id)], "updated_fields": sorted(updates)},
            )
            if patch.tags_add or patch.tags_remove:
                results.append(format_task_bulk_update_reply(
                    1,
                    updates,
                    tags_add=patch.tags_add,
                    tags_remove=patch.tags_remove,
                    language="en",
                ))
            else:
                results.append(format_task_update_reply(task, updates, language="en"))
            return

        payload = {
            "task_query": patch.task_query,
            "from_project": patch.from_project,
            "from_tags": patch.from_tags,
            "status": patch.status,
            "updates": updates,
            "tags_add": patch.tags_add,
            "tags_remove": patch.tags_remove,
            "candidate_task_ids": [str(task.id) for task in candidates],
            "agent_run_id": str(run.id),
            "language": language,
            **_call_source_payload(call),
        }
        confirmation = await self.confirmations.create(
            user,
            action_type="bulk_update_tasks",
            action_payload=payload,
            prompt=_prompt_with_evidence(
                f"Update {len(candidates)} tasks?",
                call,
            ),
        )
        await self.runs.log_tool_call(
            run=run,
            tool_name="bulk_update_tasks",
            status="requires_confirmation",
            args=args,
            result={"candidate_task_ids": [str(task.id) for task in candidates]},
            requires_confirmation=True,
            confirmation_id=confirmation.id,
        )
        results.append(
            f"Found {len(candidates)} tasks for bulk update. Confirm the action."
        )
        confirm_text = f"✓ Update {len(candidates)}"
        reject_text = "✗ No"
        buttons.append([
            Button(text=confirm_text, callback_data=f"confirm:{confirmation.id}", key="confirm"),
            Button(text=reject_text, callback_data=f"reject:{confirmation.id}", key="reject"),
        ])

    async def _resolve_update_task_candidates(
        self,
        *,
        user: User,
        patch: TaskPatchRequest,
        planner_context: PlannerContext,
    ) -> list[Task]:
        allow_done = _is_reopen_task_update(patch)
        if patch.task_id is not None:
            task = await self.tasks.get(user, patch.task_id)
            if task is not None and (task.status != TaskStatus.DONE or allow_done):
                return [task]
            return []

        if patch.recency_hint:
            ref = planner_context.task_ref_for_recency_hint(patch.recency_hint)
            if ref is not None:
                task = await self.tasks.get(user, ref.task_id)
                if task is not None and (task.status != TaskStatus.DONE or allow_done):
                    return [task]

        if patch.task_query:
            if allow_done:
                return await self.tasks.find_reopen_task_candidates(user, patch.task_query)
            return await self.tasks.find_open_rename_candidates(user, patch.task_query)

        return []

    async def _apply_rename_task_tool(
        self,
        *,
        user: User,
        run,
        call: PlannedToolCall,
        update: TaskUpdate,
        results: list[str],
        buttons: list[list[Button]],
    ) -> None:
        if update.operation == "rename":
            if _image_sourced_write(call):
                candidates = await self.tasks.find_open_rename_candidates(
                    user,
                    update.current_title,
                    project=update.project,
                    tags=update.tags,
                )
                if not candidates:
                    await self.runs.log_tool_call(
                        run=run,
                        tool_name="rename_task",
                        status="skipped",
                        args={
                            **update.model_dump(mode="json"),
                            **_call_source_payload(call),
                        },
                        result={"candidate_task_ids": []},
                    )
                    results.append(f"I could not find an active task “{update.current_title}”. Please clarify the title.")
                    return
                payload = {
                    "current_title": update.current_title,
                    "new_title": update.new_title,
                    "project": update.project,
                    "tags": update.tags,
                    "candidate_task_ids": [str(task.id) for task in candidates],
                    "agent_run_id": str(run.id),
                    **_call_source_payload(call),
                }
                confirmation = await self.confirmations.create(
                    user,
                    action_type="rename_task_choice",
                    action_payload=payload,
                    prompt=_prompt_with_evidence("Confirm the task to rename.", call),
                )
                await self.runs.log_tool_call(
                    run=run,
                    tool_name="rename_task",
                    status="requires_confirmation",
                    args=payload,
                    result={"candidate_task_ids": [str(task.id) for task in candidates]},
                    requires_confirmation=True,
                    confirmation_id=confirmation.id,
                )
                results.append("Confirmation needed: which task should I rename?")
                for index, task in enumerate(candidates[:5]):
                    buttons.append([
                        Button(
                            text=_rename_choice_button_text(task),
                            callback_data=_rename_choice_callback(confirmation.id, index),
                        )
                    ])
                return

            renamed = await self.tasks.rename_active_task_by_title(
                user,
                current_title=update.current_title,
                new_title=update.new_title,
                project=update.project,
                tags=update.tags,
                actor="agent",
                agent_run_id=run.id,
            )
            result_payload = {
                "status": renamed.status,
                "task_id": str(renamed.task.id) if renamed.task else None,
                "candidate_task_ids": [str(task.id) for task in renamed.candidates],
            }
            if renamed.status == "renamed":
                await self.runs.log_tool_call(
                    run=run,
                    tool_name="rename_task",
                    status="completed",
                    args=update.model_dump(mode="json"),
                    result=result_payload,
                )
                results.append(f"Renamed task “{renamed.old_title}” to “{renamed.new_title}”.")
            elif renamed.status == "not_found":
                await self.runs.log_tool_call(
                    run=run,
                    tool_name="rename_task",
                    status="skipped",
                    args=update.model_dump(mode="json"),
                    result=result_payload,
                )
                results.append(f"I could not find an active task “{update.current_title}”. Please clarify the title.")
            else:
                confirmation = await self.confirmations.create(
                    user,
                    action_type="rename_task_choice",
                    action_payload={
                        "current_title": update.current_title,
                        "new_title": update.new_title,
                        "project": update.project,
                        "tags": update.tags,
                        "candidate_task_ids": [str(task.id) for task in renamed.candidates],
                        "agent_run_id": str(run.id),
                    },
                    prompt="Choose the task to rename.",
                )
                await self.runs.log_tool_call(
                    run=run,
                    tool_name="rename_task",
                    status="requires_confirmation",
                    args=update.model_dump(mode="json"),
                    result=result_payload,
                    requires_confirmation=True,
                    confirmation_id=confirmation.id,
                )
                results.append("Found several matching tasks. Which one should I rename?")
                for index, task in enumerate(renamed.candidates[:5]):
                    buttons.append([
                        Button(
                            text=_rename_choice_button_text(task),
                            callback_data=_rename_choice_callback(confirmation.id, index),
                        )
                    ])
        else:
            await self.runs.log_tool_call(
                run=run,
                tool_name="rename_task",
                status="skipped",
                args=update.model_dump(mode="json"),
                result={"reason": "rename_confirmation_not_supported"},
            )

    async def _apply_complete_task_tool(
        self,
        *,
        user: User,
        run,
        call: PlannedToolCall,
        results: list[str],
        buttons: list[list[Button]],
    ) -> None:
        query = _task_query_from_call(call)
        candidates = await self.tasks.find_open_rename_candidates(
            user,
            query,
            project=call.args.get("project"),
            tags=call.args.get("tags") or [],
        )
        if len(candidates) == 1:
            if _image_sourced_write(call):
                task = candidates[0]
                args = {**call.args, **_call_source_payload(call)}
                await self.runs.log_tool_call(
                    run=run,
                    tool_name="complete_task",
                    status="requires_confirmation",
                    args=args,
                    result={"task_id": str(task.id)},
                    requires_confirmation=True,
                )
                results.append(f"Proposed marking “{task.title}” done — confirm with the button.")
                buttons.append([
                    Button(text="✓ Mark done", callback_data=f"task_done:{task.id}", key="task_done"),
                ])
                return
            task = await self.tasks.complete_task(user, candidates[0], actor="agent")
            await self.runs.log_tool_call(
                run=run,
                tool_name="complete_task",
                status="completed",
                args=call.args,
                result={"task_id": str(task.id)},
            )
            results.append(f"Marked task “{task.title}” done.")
            return
        await self.runs.log_tool_call(
            run=run,
            tool_name="complete_task",
            status="skipped",
            args=call.args,
            result={"candidate_task_ids": [str(task.id) for task in candidates]},
        )
        results.append(
            "I could not find an open task. Please clarify the title."
            if not candidates else
            "Found several matching tasks. Please clarify which one to mark done."
        )

    async def _apply_snooze_task_tool(
        self,
        *,
        user: User,
        run,
        call: PlannedToolCall,
        results: list[str],
        buttons: list[list[Button]],
    ) -> None:
        query = _task_query_from_call(call)
        candidates = await self.tasks.find_open_rename_candidates(
            user,
            query,
            project=call.args.get("project"),
            tags=call.args.get("tags") or [],
        )
        preset = str(call.args.get("preset") or "tomorrow")
        if preset not in {"1h", "3h", "tomorrow", "next_week"}:
            preset = "tomorrow"
        now = utc_now()
        visible_candidates = [
            task for task in candidates
            if task.snoozed_until is None or task.snoozed_until <= now
        ]
        if visible_candidates:
            candidates = visible_candidates
        if len(candidates) == 1:
            if _image_sourced_write(call):
                task = candidates[0]
                args = {**call.args, "preset": preset, **_call_source_payload(call)}
                await self.runs.log_tool_call(
                    run=run,
                    tool_name="snooze_task",
                    status="requires_confirmation",
                    args=args,
                    result={"task_id": str(task.id)},
                    requires_confirmation=True,
                )
                results.append(f"Proposed snoozing “{task.title}” — confirm with the button.")
                buttons.append([
                    Button(text="⏰ Snooze", callback_data=f"task_snooze:{task.id}:{preset}",
                           key="task_snooze"),
                ])
                return
            task = await self.tasks.snooze_task(user, candidates[0], preset=preset, actor="agent")
            await self.runs.log_tool_call(
                run=run,
                tool_name="snooze_task",
                status="completed",
                args={**call.args, "preset": preset},
                result={
                    "task_id": str(task.id),
                    "snoozed_until": task.snoozed_until.isoformat() if task.snoozed_until else None,
                },
            )
            when = fmt_local(task.snoozed_until, user.timezone) if task.snoozed_until else "later"
            results.append(f"Snoozed task “{task.title}” until {when}.")
            return
        if len(candidates) > 1:
            confirmation = await self.confirmations.create(
                user,
                action_type="snooze_task_choice",
                action_payload={
                    "task_query": query,
                    "preset": preset,
                    "project": call.args.get("project"),
                    "tags": call.args.get("tags") or [],
                    "candidate_task_ids": [str(task.id) for task in candidates],
                    "agent_run_id": str(run.id),
                    **_call_source_payload(call),
                },
                prompt=_prompt_with_evidence("Choose the task to snooze.", call),
            )
            await self.runs.log_tool_call(
                run=run,
                tool_name="snooze_task",
                status="requires_confirmation",
                args={**call.args, "preset": preset, **_call_source_payload(call)},
                result={"candidate_task_ids": [str(task.id) for task in candidates]},
                requires_confirmation=True,
                confirmation_id=confirmation.id,
            )
            results.append("Found several matching tasks. Which one should I snooze?")
            for index, task in enumerate(candidates[:5]):
                buttons.append([
                    Button(
                        text=_rename_choice_button_text(task),
                        callback_data=_snooze_choice_callback(confirmation.id, index),
                    )
                ])
            return
        await self.runs.log_tool_call(
            run=run,
            tool_name="snooze_task",
            status="skipped",
            args=call.args,
            result={"candidate_task_ids": [str(task.id) for task in candidates]},
        )
        results.append(
            "I could not find an open task. Please clarify the title."
            if not candidates else
            "Found several matching tasks. Please clarify which one to snooze."
        )

    async def _apply_news_digest_tool(
        self,
        *,
        user: User,
        run,
        request: NewsRequest,
        results: list[str],
    ) -> None:
        from lumi.services.news import NewsService

        service = NewsService(self.session, llm=self.llm)
        topics = [topic for topic in await service.list_topics(user) if topic.enabled]
        if not topics:
            await self.runs.log_tool_call(
                run=run,
                tool_name="news_digest",
                status="skipped",
                args=request.model_dump(mode="json"),
                result={"reason": "no_topics"},
            )
            results.append("No news topics yet — add a topic or RSS source in the Mini App.")
            return

        digest_run = await self.runs.create(
            user_id=user.id,
            type_=AgentRunType.NEWS_DIGEST,
            trigger="telegram_message",
            conversation_id=run.conversation_id,
            source_message_id=run.source_message_id,
            input_summary=", ".join(request.topics)[:300] if request.topics else "news_digest",
        )
        digest_run_id = str(digest_run.id)
        await commit_with_realtime(self.session)
        job_id = await enqueue_job(
            "run_news_digest",
            str(user.id),
            agent_run_id=digest_run_id,
            trigger="telegram_message",
            notify=True,
        )
        status = "completed" if job_id else "failed"
        await self.runs.log_tool_call(
            run=run,
            tool_name="news_digest",
            status=status,
            args=request.model_dump(mode="json"),
            result={"run_id": digest_run_id, "job_id": job_id},
        )
        if job_id:
            results.append("Started digest collection — I will send the result in a separate message.")
        else:
            results.append("The job queue is unavailable — digest collection did not start.")

    async def _apply_store_memory_tool(
        self,
        *,
        user: User,
        run,
        candidate: MemoryCandidate,
        call: PlannedToolCall,
        source_message_id: uuid.UUID,
        results: list[str],
    ) -> None:
        explicit = True
        auto = (
            (explicit and candidate.confidence >= MEMORY_EXPLICIT_CONFIDENCE)
            or (candidate.kind in ("preference", "instruction")
                and candidate.confidence >= MEMORY_IMPLICIT_CONFIDENCE)
        ) and not candidate.requires_confirmation
        if (
            explicit
            and candidate.confidence >= MEMORY_EXPLICIT_CONFIDENCE
            and not candidate.requires_confirmation
        ):
            auto = True
        if auto:
            memory, created = await self.memory.store_candidate(
                user, candidate, source_message_id=source_message_id,
                source_agent_run_id=run.id,
            )
            await self.runs.log_tool_call(
                run=run, tool_name="store_memory", status="completed",
                args=candidate.model_dump(mode="json"),
                result={"memory_id": str(memory.id), "created": created},
            )
            results.append(
                "Remembered: " + candidate.text if created
                else "Updated the existing memory note"
            )
        elif candidate.requires_confirmation and candidate.confidence >= 0.6:
            payload = {
                **candidate.model_dump(mode="json"),
                **_call_source_payload(call),
            }
            confirmation = await self.confirmations.create(
                user,
                action_type="store_memory",
                action_payload=payload,
                prompt=_prompt_with_evidence(f"Remember “{candidate.text}”?", call),
            )
            await self.runs.log_tool_call(
                run=run,
                tool_name="store_memory",
                status="requires_confirmation",
                args=payload,
                requires_confirmation=True,
                confirmation_id=confirmation.id,
            )
            results.append("Proposed saving this to memory — confirmation required.")
        elif candidate.confidence >= 0.6:
            await self.runs.log_tool_call(
                run=run, tool_name="store_memory", status="skipped",
                args=candidate.model_dump(mode="json"),
                result={"reason": "memory_auto_only"},
            )

    async def _apply_create_automation_tool(
        self,
        *,
        user: User,
        run,
        call: PlannedToolCall,
        automation: AutomationRequest,
        results: list[str],
        buttons: list[list[Button]],
    ) -> None:
        if automation.confidence < 0.6 or not automation.cron_expression:
            return
        payload = {
            **automation.model_dump(mode="json"),
            **_call_source_payload(call),
        }
        confirmation = await self.confirmations.create(
            user,
            action_type="create_automation",
            action_payload=payload,
            prompt=_prompt_with_evidence(
                f"Enable automation “{automation.title}” ({automation.cron_expression})?",
                call,
            ),
        )
        await self.runs.log_tool_call(
            run=run, tool_name="create_scheduled_task", status="requires_confirmation",
            args=payload,
            requires_confirmation=True, confirmation_id=confirmation.id,
        )
        results.append(f"Automation “{automation.title}” is prepared — confirmation required")
        buttons.append([
            Button(text="✓ Enable", callback_data=f"confirm:{confirmation.id}", key="confirm"),
            Button(text="✗ No", callback_data=f"reject:{confirmation.id}", key="reject"),
        ])

    async def _apply_read_calendar_events_tool(
        self,
        *,
        user: User,
        run,
        call: PlannedToolCall,
        request: CalendarEventsRequest,
        results: list[str],
        language: str | None,
        user_visible: bool,
    ) -> CalendarReadResult:
        start = local_to_utc(request.start_at_local, user.timezone)
        end = local_to_utc(request.end_at_local, user.timezone)
        sync_result: dict[str, int | str] | None = None
        sync_error: str | None = None
        if request.sync_if_needed:
            try:
                sync_result = await CalendarSyncService(self.session).sync_all_calendars(
                    user,
                    start_at=start,
                    end_at=end,
                )
            except Exception as exc:  # noqa: BLE001 - read DB cache even if sync is unavailable
                sync_error = str(exc)[:500]
                log.warning(
                    "calendar on-demand sync failed",
                    fields={"user_id": str(user.id), "error": sync_error},
                )

        events = await self.calendar.list_events(user, start, end)
        await self.runs.log_tool_call(
            run=run,
            tool_name="read_calendar_events",
            status="completed",
            args={
                **request.model_dump(mode="json"),
                **_call_source_payload(call),
            },
            result={
                "count": len(events),
                "sync": sync_result,
                "sync_error": sync_error,
            },
        )
        if not events:
            empty_text = _calendar_empty_text(language, sync_error=bool(sync_error))
            if user_visible:
                results.append(empty_text)
            return CalendarReadResult(
                observation_summary=empty_text,
                open_app_button=user_visible,
            )

        lines = ["Calendar events:"]
        schedule_items = schedule_items_from_calendar_events(events)
        if not request.include_details:
            schedule_items = [
                item.__class__(
                    title=item.title,
                    start_at=item.start_at,
                    end_at=item.end_at,
                    kind=item.kind,
                    action_id=item.action_id,
                    busy=item.busy,
                )
                for item in schedule_items
            ]
        schedule_window_end = end - timedelta(seconds=1) if end > start else start
        is_single_day = utc_to_local(start, user.timezone).date() == utc_to_local(
            schedule_window_end, user.timezone
        ).date()
        rendered_schedule = render_schedule_message(
            title=_calendar_window_title(language, start=start, end=end, tz=user.timezone),
            items=schedule_items,
            timezone=user.timezone,
            language=language,
            window_start=start,
            window_end=end,
            include_free_gaps=True,
            max_items=CALENDAR_TELEGRAM_EVENT_LIMIT if is_single_day else None,
        )
        for event in events[:20]:
            when = _calendar_event_when(event, user.timezone)
            line = f"{when} — {event.title}"
            location = event.metadata_.get("location")
            meeting_url = event.metadata_.get("meeting_url")
            if location:
                line += f" ({location})"
            if request.include_details and meeting_url:
                line += f" — {meeting_url}"
            lines.append(line)
        if len(events) > 20:
            lines.append(f"{len(events) - 20} more events not shown.")
        if user_visible:
            results.append(rendered_schedule.plain_text)
        return CalendarReadResult(
            observation_summary="\n".join(lines),
            reply_rich_html=rendered_schedule.rich_html if user_visible else None,
            open_app_button=user_visible,
        )

    async def _next_available_calendar_slot_after(
        self,
        user: User,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[datetime, datetime] | None:
        duration = end - start
        if duration <= timedelta(0):
            return None
        local_start = utc_to_local(start, user.timezone)
        day_start = local_to_utc(
            datetime(local_start.year, local_start.month, local_start.day, 0, 0),
            user.timezone,
        )
        day_end = local_to_utc(
            datetime(local_start.year, local_start.month, local_start.day, 23, 59, 59),
            user.timezone,
        )
        cursor = start
        events = await self.calendar.list_events(user, day_start, day_end)
        for busy_start, busy_end in merge_busy_intervals(_calendar_busy_intervals(events)):
            if busy_end <= cursor:
                continue
            candidate_end = cursor + duration
            if candidate_end <= busy_start:
                return cursor, candidate_end
            if busy_start < candidate_end and busy_end > cursor:
                cursor = max(cursor, busy_end)
        candidate_end = cursor + duration
        if candidate_end <= day_end:
            return cursor, candidate_end
        return None

    async def _apply_calendar_request(
        self,
        *,
        user: User,
        run,
        call: PlannedToolCall,
        request: CalendarRequest,
        results: list[str],
        buttons: list[list[Button]],
        outcomes: list[ActionOutcome],
        language: str,
        text: str,
    ) -> None:
        tz = user.timezone
        if request.kind == "plan_day":
            summary, created = await self.planning.propose_day_plan(
                user, agent_run_id=run.id
            )
            await self.runs.log_tool_call(
                run=run, tool_name="propose_day_plan", status="completed",
                args=request.model_dump(mode="json"),
                result={"blocks": len(created)},
            )
            results.append("Prepared day plan: " + summary.split("\n")[0])
            for event in created:
                buttons.append([
                    Button(
                        text=f"✓ Accept {utc_to_local(event.start_at, tz).strftime('%H:%M')} {event.title[:20]}",
                        callback_data=f"block_confirm:{event.id}",
                    )
                ])
            return

        if request.kind == "find_focus_slot":
            duration = max(15, min(request.duration_minutes or 60, 240))
            day = (
                local_to_utc(request.time_window_local.start, tz)
                if request.time_window_local
                else None
            )
            from lumi.utils.time import utc_now

            slots = await self.calendar.find_free_slots(
                user, day=day or utc_now(), duration_minutes=duration
            )
            if not slots:
                results.append("No free window for a focus block was found today.")
                return
            start, _ = slots[0]
            end = start + timedelta(minutes=duration)
            title = request.title or "Focus block"
            event = await self.calendar.create_internal_block(
                user,
                title=title,
                description=request.description,
                start_at=start,
                end_at=end,
                status=CalendarEventStatus.PROPOSED,
                created_by="agent",
                agent_run_id=run.id,
                metadata={"reply_language": language},
            )
            await self.runs.log_tool_call(
                run=run, tool_name="create_internal_calendar_block", status="completed",
                args=request.model_dump(mode="json"),
                result={"event_id": str(event.id), "status": "proposed"},
            )
            results.append(
                f"Found a {utc_to_local(start, tz).strftime('%H:%M')}–"
                f"{utc_to_local(end, tz).strftime('%H:%M')} window for “{title}” (proposed)"
            )
            buttons.append([
                Button(
                    text=_accept_block_button_text(language),
                    callback_data=f"block_confirm:{event.id}",
                    key="block_confirm",
                ),
            ])
            return

        if request.kind == "create_internal_block":
            if not request.start_at_local or not request.end_at_local or request.confidence < 0.75:
                return
            title = request.title or "Block"
            start_at = local_to_utc(request.start_at_local, tz)
            end_at = local_to_utc(request.end_at_local, tz)
            if end_at <= start_at:
                return
            requested_start_at = start_at
            requested_end_at = end_at
            conflicts = await self.calendar.list_events(user, start_at, end_at)
            busy_conflicts = [
                event for event in conflicts
                if event.busy and event.status in (
                    CalendarEventStatus.CONFIRMED,
                    CalendarEventStatus.TENTATIVE,
                    CalendarEventStatus.PROPOSED,
                )
            ]
            if busy_conflicts:
                adjusted = (
                    await self._next_available_calendar_slot_after(user, start=start_at, end=end_at)
                    if _looks_like_flexible_calendar_slot_request(text)
                    else None
                )
                if adjusted is None:
                    conflict = busy_conflicts[0]
                    start_label = utc_to_local(start_at, tz).strftime("%H:%M")
                    end_label = utc_to_local(end_at, tz).strftime("%H:%M")
                    fallback = _calendar_conflict_text(
                        language,
                        title=title,
                        conflict_title=conflict.title,
                        start_label=start_label,
                        end_label=end_label,
                    )
                    await self.runs.log_tool_call(
                        run=run,
                        tool_name="create_internal_calendar_block",
                        status="skipped",
                        args={**request.model_dump(mode="json"), **_call_source_payload(call)},
                        result={
                            "reason": "calendar_conflict",
                            "conflict_event_id": str(conflict.id),
                            "conflict_title": conflict.title,
                        },
                    )
                    results.append(fallback)
                    outcomes.append(ActionOutcome(
                        action_type="create_internal_calendar_block",
                        status="skipped",
                        fallback_text=fallback,
                        title=title,
                        error_code="calendar_conflict",
                        details={"conflict_event_id": str(conflict.id)},
                    ))
                    return
                start_at, end_at = adjusted
            requires_confirmation = request.requires_confirmation
            event = await self.calendar.create_internal_block(
                user,
                title=title,
                description=request.description,
                start_at=start_at,
                end_at=end_at,
                status=(
                    CalendarEventStatus.PROPOSED
                    if requires_confirmation else CalendarEventStatus.CONFIRMED
                ),
                created_by="agent",
                agent_run_id=run.id,
                metadata={
                    "reply_language": language,
                    **({
                        "adjusted_from_start_at": requested_start_at.isoformat(),
                        "adjusted_from_end_at": requested_end_at.isoformat(),
                    } if (start_at, end_at) != (requested_start_at, requested_end_at) else {}),
                },
            )
            await self.runs.log_tool_call(
                run=run,
                tool_name="create_internal_calendar_block",
                status="requires_confirmation" if requires_confirmation else "completed",
                args={**request.model_dump(mode="json"), **_call_source_payload(call)},
                result={"event_id": str(event.id), "status": event.status.value},
                requires_confirmation=requires_confirmation,
            )
            if requires_confirmation:
                start_label = fmt_local(event.start_at, tz, "%d.%m %H:%M")
                results.append(
                    _calendar_proposed_text(language, title=title, start_label=start_label)
                )
                buttons.append([
                    Button(
                        text=_accept_block_button_text(language),
                        callback_data=f"block_confirm:{event.id}",
                        key="block_confirm",
                    ),
                ])
            else:
                start_label = fmt_local(event.start_at, tz, "%d.%m %H:%M")
                results.append(
                    _calendar_added_text(language, title=title, start_label=start_label)
                )
            return

        if request.kind == "create_external_event":
            # External writes ALWAYS require confirmation.
            payload = {
                **request.model_dump(mode="json"),
                **_call_source_payload(call),
            }
            confirmation = await self.confirmations.create(
                user,
                action_type="create_google_calendar_event",
                action_payload=payload,
                prompt=_prompt_with_evidence(
                    f"Add “{request.title or 'event'}” to Google Calendar?",
                    call,
                ),
            )
            await self.runs.log_tool_call(
                run=run, tool_name="create_external_calendar_event",
                status="requires_confirmation",
                args=payload,
                requires_confirmation=True, confirmation_id=confirmation.id,
            )
            results.append("External calendar write is waiting for confirmation.")
            buttons.append([
                Button(text="📅 Add to Google Calendar",
                       callback_data=f"confirm:{confirmation.id}", key="confirm"),
                Button(text="✗ No", callback_data=f"reject:{confirmation.id}", key="reject"),
            ])
