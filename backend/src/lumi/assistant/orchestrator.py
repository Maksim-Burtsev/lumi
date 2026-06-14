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
from lumi.assistant.planner import AgentPlanner
from lumi.assistant.schemas import (
    AgentPlan,
    AutomationRequest,
    CalendarRequest,
    EmailRequest,
    ExtractedTask,
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
    args.setdefault("requires_confirmation", call.requires_confirmation)
    return args


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

        # 4. Planner call (separate small call — reliable and predictable;
        # a combined signals+reply call made M3 reason for minutes, parked for now)
        await progress("🧠 Разбираю сообщение…")
        plan = await self.planner.plan(
            user=user, text=text, agent_run_id=run.id, session=self.session
        )

        # 5. Apply safe actions
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
        needs_compaction = await self._needs_compaction(conversation)

        return AssistantResult(
            reply_text=reply_text,
            buttons=buttons,
            agent_run_id=run.id,
            needs_compaction=needs_compaction,
        )

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
                    user=user, run=run, request=request, results=results, buttons=buttons
                )
            elif call.name == "create_automation":
                automation = AutomationRequest.model_validate(_args_with_call_defaults(call))
                await self._apply_create_automation_tool(user=user, run=run,
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
        update: TaskUpdate,
        results: list[str],
        buttons: list[list[Button]],
    ) -> None:
        if update.operation == "rename":
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
                },
                prompt="Выбери задачу для откладывания.",
            )
            await self.runs.log_tool_call(
                run=run,
                tool_name="snooze_task",
                status="requires_confirmation",
                args={**call.args, "preset": preset},
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
        source_message_id: uuid.UUID,
        results: list[str],
    ) -> None:
        explicit = True
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

    async def _apply_create_automation_tool(
        self,
        *,
        user: User,
        run,
        automation: AutomationRequest,
        results: list[str],
        buttons: list[list[Button]],
    ) -> None:
        if automation.confidence < 0.6 or not automation.cron_expression:
            return
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
