"""AssistantOrchestrator: the chat pipeline.

save message -> extract signals -> apply safe actions -> build context ->
final LLM reply -> save reply -> (maybe) compaction flag.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.context_builder import ContextBuilder
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
    CalendarRequest,
    EmailRequest,
    ExtractedTask,
    FocusedVisionRequest,
    MediaUnderstanding,
    MemoryCandidate,
    NewsRequest,
    PlannedToolCall,
    TaskUpdate,
)
from lumi.db.models import (
    AgentRunType,
    CalendarEventStatus,
    Message,
    MessageRole,
    Task,
    User,
)
from lumi.llm.gateway import LLMGateway
from lumi.logging import agent_run_id_var, get_logger
from lumi.services.calendar import CalendarService
from lumi.services.confirmations import ConfirmationService
from lumi.services.planning import PlanningService
from lumi.services.runs import RunService
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.utils.text import truncate
from lumi.utils.time import fmt_local, local_to_utc, utc_now, utc_to_local
from lumi.worker.queue import enqueue_job

log = get_logger(__name__)

TASK_AUTO_CREATE_CONFIDENCE = 0.85
TASK_CONFIRM_CONFIDENCE = 0.5
MEMORY_EXPLICIT_CONFIDENCE = 0.85
MEMORY_IMPLICIT_CONFIDENCE = 0.92
FALLBACK_REPLY = (
    "Я не смог сейчас достучаться до модели. Сообщение сохранил, можно повторить через минуту."
)
FOCUSED_VISION_UNSAFE_REPLY = (
    "Не могу безопасно выполнить это через изображение. Уточни, что именно нужно рассмотреть."
)
MEDIA_REQUIRED_REPLY = "Пришли картинку или ответь на сообщение с картинкой, которую нужно разобрать."
IMAGE_SOURCED_CONFIRM_TOOLS = {
    "create_task",
    "rename_task",
    "complete_task",
    "snooze_task",
    "store_memory",
    "create_internal_calendar_block",
    "create_external_calendar_event",
    "create_automation",
}
ACTION_DONE_CLAIM_TERMS = (
    "готово",
    "сделал",
    "добавил",
    "создал",
    "записал",
    "сохранил",
    "назначил",
    "запланировал",
    "отметил",
    "переименовал",
    "done",
    "created",
    "added",
    "scheduled",
)
ImageLoader = Callable[[dict], Awaitable[ImageInput | None]]


@dataclass(slots=True)
class Button:
    text: str
    callback_data: str


@dataclass(slots=True)
class AssistantResult:
    reply_text: str
    buttons: list[list[Button]] = field(default_factory=list)
    agent_run_id: uuid.UUID | None = None
    needs_compaction: bool = False
    open_app_button: bool = False


def _rename_choice_button_text(task: Task) -> str:
    parts = [truncate(task.title, 56)]
    if task.project:
        parts.append(task.project)
    parts.extend(f"#{tag.lstrip('#')}" for tag in (task.tags or []) if tag)
    return " · ".join(parts)


def _rename_choice_callback(confirmation_id: uuid.UUID, index: int) -> str:
    return f"rename_pick:{confirmation_id.hex[:12]}:{index}"


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
    return f"{prompt}\nИзвлечено из изображения:\n{facts}"


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


def _completion_claim_without_actions(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False
    if lowered.startswith(("готово", "сделал", "done")):
        return True
    return any(f" {term}" in f" {lowered[:160]}" for term in ACTION_DONE_CLAIM_TERMS)


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
        self.context_builder = ContextBuilder(session)
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
        image_loader: ImageLoader | None = None,
        on_progress=None,
        on_reply_delta=None,
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
        )
        conversation = await self.users.ensure_main_conversation(user)
        image_metadata = [image.to_metadata()] if image else []
        stored_text = text.strip() or ("[image]" if image else "")
        final_text = text.strip() or ("Опиши изображение и ответь на вопрос пользователя." if image else "")

        # 2. Save inbound message
        inbound = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.USER,
            content=stored_text,
            content_json={"text": text, "images": image_metadata} if image_metadata else None,
            char_count=len(stored_text),
            telegram_message_id=telegram_message_id,
            telegram_chat_id=telegram_chat_id,
            metadata_={"images": image_metadata} if image_metadata else {},
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
            await progress("👁️ Разбираю изображение…")
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

        recent_media = await self._recent_media_candidates(conversation.id, exclude_message_id=inbound.id)
        available_media = _dedupe_media_candidates(
            ([current_media] if current_media is not None else []) + recent_media
        )

        # 5. Planner call (separate small call — reliable and predictable;
        # a combined signals+reply call made M3 reason for minutes, parked for now)
        await progress("🧠 Разбираю сообщение…")
        plan = await self.planner.plan(
            user=user,
            text=text,
            media_context=media_context,
            available_media=available_media,
            agent_run_id=run.id,
            session=self.session,
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

            await progress("👁️ Разбираю изображение…")
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
                media_context=media_context,
                available_media=available_media,
                agent_run_id=run.id,
                session=self.session,
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
                    "Не выполняю действия по изображению без явной команды пользователя."
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

        if plan.mode == "needs_focused_vision":
            if selected_media is not None and selected_image is None:
                selected_image = await self._ensure_candidate_image(selected_media, image_loader)
            if selected_media is not None and media_context is None and selected_image is not None:
                await progress("👁️ Разбираю изображение…")
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

            await progress("🔎 Уточняю деталь на изображении…")
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
                "Не смог уверенно рассмотреть эту деталь на изображении."
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

        # 6. Apply safe actions
        if plan.tool_calls:
            await progress("⚙️ Выполняю: задачи, память, календарь…")
        action_results, buttons = await self._apply_tool_calls(
            user=user, run=run, plan=plan, source_message_id=inbound.id
        )

        if action_results and not plan.should_answer_normally:
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
            )

        # 6-7. Final reply
        await progress(
            "✍️ Формулирую ответ…" if not action_results
            else "✍️ Сделал: " + "; ".join(r.split(":")[0] for r in action_results[:2]) + ". Пишу ответ…"
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
            if not action_results and _completion_claim_without_actions(reply_text):
                reply_text = "Не выполнял действий. Если нужно действие, напиши его явно."
            run.metadata_ = {**run.metadata_, "context_snapshot": context.debug_snapshot}
        except Exception as exc:  # noqa: BLE001 — chat must answer something
            log.exception("final LLM reply failed")
            await self.runs.mark_failed(run, f"final_chat: {exc}")
            if action_results:
                done = "\n".join(f"• {r}" for r in action_results)
                reply_text = f"Сделал:\n{done}\n\nА вот ответить умно не вышло — модель недоступна."
            else:
                reply_text = FALLBACK_REPLY
            outbound = Message(
                conversation_id=conversation.id,
                user_id=user.id,
                role=MessageRole.ASSISTANT,
                content=reply_text,
                char_count=len(reply_text),
            )
            self.session.add(outbound)
            return AssistantResult(reply_text=reply_text, buttons=buttons, agent_run_id=run.id)

        # 8. Save assistant message
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
        return "Сделал:\n" + "\n".join(f"• {result}" for result in action_results)

    async def _needs_compaction(self, conversation) -> bool:
        from lumi.assistant.compaction import CompactionService

        return await CompactionService(self.session, llm=self.llm).needs_compaction(conversation)

    # ------------------------------------------------------------------

    async def _apply_tool_calls(
        self,
        *,
        user: User,
        run,
        plan: AgentPlan,
        source_message_id: uuid.UUID,
    ) -> tuple[list[str], list[list[Button]]]:
        results: list[str] = []
        buttons: list[list[Button]] = []

        for call in plan.tool_calls:
            if call.name == "create_task":
                task_signal = ExtractedTask.model_validate(_args_with_call_defaults(call))
                await self._apply_create_task_tool(
                    user=user,
                    run=run,
                    call=call,
                    task_signal=task_signal,
                    source_message_id=source_message_id,
                    results=results,
                    buttons=buttons,
                )
            elif call.name == "read_tasks":
                await self._apply_read_tasks_tool(
                    user=user,
                    run=run,
                    call=call,
                    results=results,
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
                    buttons=buttons
                )
            elif call.name == "create_automation":
                automation = AutomationRequest.model_validate(_args_with_call_defaults(call))
                await self._apply_create_automation_tool(user=user, run=run,
                                                         call=call,
                                                         automation=automation,
                                                         results=results, buttons=buttons)
            elif call.name == "email_triage":
                request = EmailRequest.model_validate({"kind": "triage", **call.args})
                if request.confidence >= 0.0:
                    buttons.append([Button(text="📬 Разобрать почту", callback_data="run:email_triage")])
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

        return results, buttons

    async def _apply_create_task_tool(
        self,
        *,
        user: User,
        run,
        call: PlannedToolCall,
        task_signal: ExtractedTask,
        source_message_id: uuid.UUID,
        results: list[str],
        buttons: list[list[Button]],
    ) -> None:
        if task_signal.confidence >= TASK_AUTO_CREATE_CONFIDENCE and not task_signal.requires_confirmation:
            task = await self.tasks.create_task_from_signal(
                user, task_signal, source_message_id=source_message_id, agent_run_id=run.id
            )
            await self.runs.log_tool_call(
                run=run, tool_name="create_task", status="completed",
                args=task_signal.model_dump(mode="json"),
                result={"task_id": str(task.id)},
            )
            desc = f"Создана задача: «{task.title}»"
            if task.reminder_at:
                desc += f", напоминание {fmt_local(task.reminder_at, user.timezone)}"
            elif task.due_at:
                desc += f", срок {fmt_local(task.due_at, user.timezone)}"
            results.append(desc)
            buttons.append([
                Button(text="✓ Выполнено", callback_data=f"task_done:{task.id}"),
                Button(text="⏰ Отложить", callback_data=f"task_snooze:{task.id}:tomorrow"),
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
                prompt=_prompt_with_evidence(f"Создать задачу «{task_signal.title}»?", call),
            )
            await self.runs.log_tool_call(
                run=run, tool_name="create_task", status="requires_confirmation",
                args=payload,
                requires_confirmation=True, confirmation_id=confirmation.id,
            )
            results.append(f"Предложена задача «{task_signal.title}» — ждет подтверждения")
            buttons.append([
                Button(text=f"✓ Создать: {task_signal.title[:28]}",
                       callback_data=f"confirm:{confirmation.id}"),
                Button(text="✗ Не надо", callback_data=f"reject:{confirmation.id}"),
            ])

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
            results.append("Открытых задач нет." if filter_ != "done" else "Готовых задач нет.")
            return
        lines = ["Открытые задачи:" if filter_ != "done" else "Готовые задачи:"]
        for index, task in enumerate(tasks, start=1):
            meta: list[str] = [task.priority.value]
            if task.project:
                meta.append(task.project)
            meta.extend(f"#{tag}" for tag in (task.tags or [])[:3])
            lines.append(f"{index}. {task.title} — " + ", ".join(meta))
        results.append("\n".join(lines))

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
                    results.append(f"Не нашёл активную задачу «{update.current_title}». Уточни название.")
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
                    prompt=_prompt_with_evidence("Подтверди задачу для переименования.", call),
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
                results.append("Нужно подтверждение: какую задачу переименовать?")
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
                results.append(f"Готово: переименовал «{renamed.old_title}» → «{renamed.new_title}».")
            elif renamed.status == "not_found":
                await self.runs.log_tool_call(
                    run=run,
                    tool_name="rename_task",
                    status="skipped",
                    args=update.model_dump(mode="json"),
                    result=result_payload,
                )
                results.append(f"Не нашёл активную задачу «{update.current_title}». Уточни название.")
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
                    prompt="Выбери задачу для переименования.",
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
                results.append("Нашёл несколько похожих задач. Какую переименовать?")
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
                results.append(f"Предлагаю отметить «{task.title}» выполненной — подтверди кнопкой.")
                buttons.append([
                    Button(text="✓ Отметить выполненной", callback_data=f"task_done:{task.id}"),
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
            results.append(f"Готово: отметил «{task.title}» выполненной.")
            return
        await self.runs.log_tool_call(
            run=run,
            tool_name="complete_task",
            status="skipped",
            args=call.args,
            result={"candidate_task_ids": [str(task.id) for task in candidates]},
        )
        results.append(
            "Не нашёл открытую задачу. Уточни название."
            if not candidates else
            "Нашёл несколько похожих задач. Уточни, какую отметить выполненной."
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
                results.append(f"Предлагаю отложить «{task.title}» — подтверди кнопкой.")
                buttons.append([
                    Button(text="⏰ Отложить", callback_data=f"task_snooze:{task.id}:{preset}"),
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
            when = fmt_local(task.snoozed_until, user.timezone) if task.snoozed_until else "позже"
            results.append(f"Готово: отложил «{task.title}» до {when}.")
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
                prompt=_prompt_with_evidence("Выбери задачу для откладывания.", call),
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
            results.append("Нашёл несколько похожих задач. Какую отложить?")
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
            "Не нашёл открытую задачу. Уточни название."
            if not candidates else
            "Нашёл несколько похожих задач. Уточни, какую отложить."
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
            results.append("Новостных тем пока нет — добавь тему или RSS-источник в Mini App.")
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
        await self.session.commit()
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
            results.append("Запустил сбор дайджеста — пришлю результат отдельным сообщением.")
        else:
            results.append("Очередь задач недоступна — дайджест сейчас не запустился.")

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
                "Запомнил: " + candidate.text if created
                else "Обновил существующую заметку в памяти"
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
                prompt=_prompt_with_evidence(f"Запомнить: «{candidate.text}»?", call),
            )
            await self.runs.log_tool_call(
                run=run,
                tool_name="store_memory",
                status="requires_confirmation",
                args=payload,
                requires_confirmation=True,
                confirmation_id=confirmation.id,
            )
            results.append("Предлагаю сохранить это в память — нужно подтверждение.")
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
                f"Включить автоматизацию «{automation.title}» ({automation.cron_expression})?",
                call,
            ),
        )
        await self.runs.log_tool_call(
            run=run, tool_name="create_scheduled_task", status="requires_confirmation",
            args=payload,
            requires_confirmation=True, confirmation_id=confirmation.id,
        )
        results.append(f"Автоматизация «{automation.title}» подготовлена — нужно подтверждение")
        buttons.append([
            Button(text="✓ Включить", callback_data=f"confirm:{confirmation.id}"),
            Button(text="✗ Не надо", callback_data=f"reject:{confirmation.id}"),
        ])

    async def _apply_calendar_request(
        self,
        *,
        user: User,
        run,
        call: PlannedToolCall,
        request: CalendarRequest,
        results: list[str],
        buttons: list[list[Button]],
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
            results.append("Собран план дня: " + summary.split("\n")[0])
            for event in created:
                buttons.append([
                    Button(
                        text=f"✓ Принять {utc_to_local(event.start_at, tz).strftime('%H:%M')} {event.title[:20]}",
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
                results.append("Свободных окон под фокус-блок сегодня не нашлось")
                return
            start, _ = slots[0]
            end = start + timedelta(minutes=duration)
            title = request.title or "Фокус-блок"
            event = await self.calendar.create_internal_block(
                user,
                title=title,
                start_at=start,
                end_at=end,
                status=CalendarEventStatus.PROPOSED,
                created_by="agent",
                agent_run_id=run.id,
            )
            await self.runs.log_tool_call(
                run=run, tool_name="create_internal_calendar_block", status="completed",
                args=request.model_dump(mode="json"),
                result={"event_id": str(event.id), "status": "proposed"},
            )
            results.append(
                f"Нашел окно {utc_to_local(start, tz).strftime('%H:%M')}–"
                f"{utc_to_local(end, tz).strftime('%H:%M')} под «{title}» (предложено)"
            )
            buttons.append([
                Button(text="✓ Принять блок", callback_data=f"block_confirm:{event.id}"),
            ])
            return

        if request.kind == "create_internal_block":
            if not request.start_at_local or not request.end_at_local or request.confidence < 0.75:
                return
            requires_confirmation = request.requires_confirmation
            event = await self.calendar.create_internal_block(
                user,
                title=request.title or "Блок",
                start_at=local_to_utc(request.start_at_local, tz),
                end_at=local_to_utc(request.end_at_local, tz),
                status=(
                    CalendarEventStatus.PROPOSED
                    if requires_confirmation else CalendarEventStatus.CONFIRMED
                ),
                created_by="agent",
                agent_run_id=run.id,
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
                results.append(
                    f"Предложил блок «{request.title or 'блок'}» "
                    f"{fmt_local(event.start_at, tz, '%d.%m %H:%M')} — нужно подтверждение"
                )
                buttons.append([
                    Button(text="✓ Принять блок", callback_data=f"block_confirm:{event.id}"),
                ])
            else:
                results.append(
                    f"Поставил в календарь: {request.title or 'блок'} "
                    f"{fmt_local(event.start_at, tz, '%d.%m %H:%M')}"
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
                    f"Добавить «{request.title or 'событие'}» в Google Calendar?",
                    call,
                ),
            )
            await self.runs.log_tool_call(
                run=run, tool_name="create_external_calendar_event",
                status="requires_confirmation",
                args=payload,
                requires_confirmation=True, confirmation_id=confirmation.id,
            )
            results.append("Запись во внешний календарь ждет подтверждения")
            buttons.append([
                Button(text="📅 Добавить в Google Calendar",
                       callback_data=f"confirm:{confirmation.id}"),
                Button(text="✗ Не надо", callback_data=f"reject:{confirmation.id}"),
            ])
