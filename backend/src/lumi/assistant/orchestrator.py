"""AssistantOrchestrator: the chat pipeline.

save message -> extract signals -> apply safe actions -> build context ->
final LLM reply -> save reply -> (maybe) compaction flag.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.context_builder import ContextBuilder
from lumi.assistant.memory_service import MemoryService
from lumi.assistant.schemas import CalendarRequest, ExtractedSignals
from lumi.assistant.signal_extractor import SignalExtractor
from lumi.db.models import (
    AgentRunType,
    CalendarEventStatus,
    Message,
    MessageRole,
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
from lumi.utils.time import fmt_local, local_to_utc, utc_to_local

log = get_logger(__name__)

TASK_AUTO_CREATE_CONFIDENCE = 0.85
TASK_CONFIRM_CONFIDENCE = 0.5
MEMORY_EXPLICIT_CONFIDENCE = 0.85
MEMORY_IMPLICIT_CONFIDENCE = 0.92
FALLBACK_REPLY = (
    "Я не смог сейчас достучаться до модели. Сообщение сохранил, можно повторить через минуту."
)


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
        self.extractor = SignalExtractor(self.llm)
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

        # 2. Save inbound message
        inbound = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.USER,
            content=text,
            char_count=len(text),
            telegram_message_id=telegram_message_id,
            telegram_chat_id=telegram_chat_id,
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
            input_summary=text[:300],
        )
        await self.runs.mark_running(run)
        agent_run_id_var.set(str(run.id))

        # 4. Signal extraction (separate small call — reliable and predictable;
        # a combined signals+reply call made M3 reason for minutes, parked for now)
        await progress("🧠 Разбираю сообщение…")
        signals = await self.extractor.extract(
            user=user, text=text, agent_run_id=run.id, session=self.session
        )

        # 5. Apply safe actions
        if signals.tasks or signals.memory_candidates or signals.calendar_requests \
                or signals.automation_requests:
            await progress("⚙️ Выполняю: задачи, память, календарь…")
        action_results, buttons = await self._apply_signals(
            user=user, run=run, signals=signals, source_message_id=inbound.id
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
                current_text=text,
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
        from lumi.assistant.compaction import CompactionService

        needs_compaction = await CompactionService(self.session, llm=self.llm).needs_compaction(
            conversation
        )

        return AssistantResult(
            reply_text=reply_text,
            buttons=buttons,
            agent_run_id=run.id,
            needs_compaction=needs_compaction,
        )

    # ------------------------------------------------------------------

    async def _apply_signals(
        self,
        *,
        user: User,
        run,
        signals: ExtractedSignals,
        source_message_id: uuid.UUID,
    ) -> tuple[list[str], list[list[Button]]]:
        results: list[str] = []
        buttons: list[list[Button]] = []

        # --- tasks -----------------------------------------------------
        for task_signal in signals.tasks:
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
                confirmation = await self.confirmations.create(
                    user,
                    action_type="create_task",
                    action_payload=task_signal.model_dump(mode="json"),
                    prompt=f"Создать задачу «{task_signal.title}»?",
                )
                await self.runs.log_tool_call(
                    run=run, tool_name="create_task", status="requires_confirmation",
                    args=task_signal.model_dump(mode="json"),
                    requires_confirmation=True, confirmation_id=confirmation.id,
                )
                results.append(f"Предложена задача «{task_signal.title}» — ждет подтверждения")
                buttons.append([
                    Button(text=f"✓ Создать: {task_signal.title[:28]}",
                           callback_data=f"confirm:{confirmation.id}"),
                    Button(text="✗ Не надо", callback_data=f"reject:{confirmation.id}"),
                ])

        # --- memories ---------------------------------------------------
        for candidate in signals.memory_candidates:
            explicit = "store_memory" in signals.intents
            auto = (
                (explicit and candidate.confidence >= MEMORY_EXPLICIT_CONFIDENCE)
                or (candidate.kind in ("preference", "instruction")
                    and candidate.confidence >= MEMORY_IMPLICIT_CONFIDENCE)
            ) and not candidate.requires_confirmation
            if explicit and candidate.confidence >= MEMORY_EXPLICIT_CONFIDENCE:
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
            elif candidate.confidence >= 0.6:
                await self.runs.log_tool_call(
                    run=run, tool_name="store_memory", status="skipped",
                    args=candidate.model_dump(mode="json"),
                    result={"reason": "memory_auto_only"},
                )

        # --- calendar ---------------------------------------------------
        for request in signals.calendar_requests:
            await self._apply_calendar_request(
                user=user, run=run, request=request, results=results, buttons=buttons
            )

        # --- automations -------------------------------------------------
        for automation in signals.automation_requests:
            if automation.confidence < 0.6 or not automation.cron_expression:
                continue
            confirmation = await self.confirmations.create(
                user,
                action_type="create_automation",
                action_payload=automation.model_dump(mode="json"),
                prompt=f"Включить автоматизацию «{automation.title}» ({automation.cron_expression})?",
            )
            await self.runs.log_tool_call(
                run=run, tool_name="create_scheduled_task", status="requires_confirmation",
                args=automation.model_dump(mode="json"),
                requires_confirmation=True, confirmation_id=confirmation.id,
            )
            results.append(f"Автоматизация «{automation.title}» подготовлена — нужно подтверждение")
            buttons.append([
                Button(text="✓ Включить", callback_data=f"confirm:{confirmation.id}"),
                Button(text="✗ Не надо", callback_data=f"reject:{confirmation.id}"),
            ])

        # --- email / news intents ----------------------------------------
        if any(r.kind == "triage" for r in signals.email_requests):
            buttons.append([Button(text="📬 Разобрать почту", callback_data="run:email_triage")])
        if any(r.kind == "digest" for r in signals.news_requests):
            buttons.append([Button(text="📰 Собрать дайджест", callback_data="run:news_digest")])

        return results, buttons

    async def _apply_calendar_request(
        self,
        *,
        user: User,
        run,
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
            event = await self.calendar.create_internal_block(
                user,
                title=request.title or "Блок",
                start_at=local_to_utc(request.start_at_local, tz),
                end_at=local_to_utc(request.end_at_local, tz),
                created_by="agent",
                agent_run_id=run.id,
            )
            await self.runs.log_tool_call(
                run=run, tool_name="create_internal_calendar_block", status="completed",
                args=request.model_dump(mode="json"), result={"event_id": str(event.id)},
            )
            results.append(
                f"Поставил в календарь: {request.title or 'блок'} "
                f"{fmt_local(event.start_at, tz, '%d.%m %H:%M')}"
            )
            return

        if request.kind == "create_external_event":
            # External writes ALWAYS require confirmation.
            confirmation = await self.confirmations.create(
                user,
                action_type="create_google_calendar_event",
                action_payload=request.model_dump(mode="json"),
                prompt=f"Добавить «{request.title or 'событие'}» в Google Calendar?",
            )
            await self.runs.log_tool_call(
                run=run, tool_name="create_external_calendar_event",
                status="requires_confirmation",
                args=request.model_dump(mode="json"),
                requires_confirmation=True, confirmation_id=confirmation.id,
            )
            results.append("Запись во внешний календарь ждет подтверждения")
            buttons.append([
                Button(text="📅 Добавить в Google Calendar",
                       callback_data=f"confirm:{confirmation.id}"),
                Button(text="✗ Не надо", callback_data=f"reject:{confirmation.id}"),
            ])
