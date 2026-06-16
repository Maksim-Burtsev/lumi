"""EmailService: Gmail sync (read-only) + LLM triage + task candidates."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.prompts import EMAIL_TRIAGE_SYSTEM
from lumi.assistant.schemas import TriageResult
from lumi.config import get_settings
from lumi.connectors.google.gmail import GmailConnector
from lumi.db.models import EmailCategory, EmailMessage, EmailThread, User
from lumi.llm.base import LLMMessage
from lumi.llm.gateway import LLMGateway
from lumi.logging import get_logger
from lumi.services.realtime import RealtimeEventService
from lumi.utils.time import utc_now

log = get_logger(__name__)

TRIAGE_WINDOW = timedelta(hours=36)
MAX_THREADS_PER_TRIAGE = 40


class EmailService:
    def __init__(self, session: AsyncSession, *, llm: LLMGateway | None = None,
                 connector: GmailConnector | None = None) -> None:
        self.session = session
        self.llm = llm or LLMGateway()
        self.connector = connector or GmailConnector()

    # --- sync -----------------------------------------------------------

    async def sync_recent_threads(self, user: User, *, since=None) -> list[EmailThread]:
        """Pull recent Gmail threads and upsert metadata. Raises GoogleNotConnectedError."""
        settings = get_settings()
        since = since or (utc_now() - TRIAGE_WINDOW)
        dtos = await self.connector.list_recent_threads(
            since=since,
            max_results=MAX_THREADS_PER_TRIAGE,
            include_bodies=settings.store_email_bodies,
        )
        threads: list[EmailThread] = []
        for dto in dtos:
            result = await self.session.execute(
                select(EmailThread).where(
                    EmailThread.user_id == user.id,
                    EmailThread.provider == "google",
                    EmailThread.external_thread_id == dto.external_thread_id,
                )
            )
            thread = result.scalar_one_or_none()
            if thread is None:
                thread = EmailThread(
                    user_id=user.id, provider="google",
                    external_thread_id=dto.external_thread_id,
                )
                self.session.add(thread)
            thread.subject = dto.subject
            thread.participants = dto.participants
            thread.labels = dto.labels
            thread.snippet = dto.snippet
            thread.last_message_at = dto.last_message_at
            await self.session.flush()

            for msg_dto in dto.messages:
                existing = await self.session.execute(
                    select(EmailMessage.id).where(
                        EmailMessage.user_id == user.id,
                        EmailMessage.provider == "google",
                        EmailMessage.external_message_id == msg_dto.external_message_id,
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    continue
                self.session.add(
                    EmailMessage(
                        thread_id=thread.id,
                        user_id=user.id,
                        provider="google",
                        external_message_id=msg_dto.external_message_id,
                        sender=msg_dto.sender,
                        recipients=msg_dto.recipients,
                        cc=msg_dto.cc,
                        subject=msg_dto.subject,
                        snippet=msg_dto.snippet,
                        body_text=msg_dto.body_text if settings.store_email_bodies else None,
                        date_at=msg_dto.date_at,
                    )
                )
            threads.append(thread)
        if threads:
            await RealtimeEventService(self.session).emit(
                user_id=user.id,
                topics=["inbox"],
                event_type="inbox.synced",
                payload={"thread_count": len(threads)},
            )
        return threads

    # --- triage -----------------------------------------------------------

    async def triage_inbox(
        self, user: User, *, agent_run_id: uuid.UUID | None = None
    ) -> tuple[TriageResult, list[EmailThread]]:
        """Sync + classify recent threads. Returns (triage result, affected threads)."""
        threads = await self.sync_recent_threads(user)
        if not threads:
            return TriageResult(
                summary="Новых писем нет.",
                telegram_digest="Почта: новых писем за последние 36 часов нет.",
            ), []

        lines = []
        for t in threads:
            sender = t.participants[0] if t.participants else "?"
            lines.append(
                json.dumps(
                    {
                        "external_thread_id": t.external_thread_id,
                        "from": sender,
                        "subject": t.subject or "(без темы)",
                        "snippet": (t.snippet or "")[:300],
                        "labels": t.labels[:5],
                    },
                    ensure_ascii=False,
                )
            )
        user_content = (
            f"Писем/тредов: {len(threads)}. Каждый тред — JSON-строка:\n" + "\n".join(lines)
        )

        raw = await self.llm.complete_json(
            messages=[LLMMessage(role="user", content=user_content)],
            system=EMAIL_TRIAGE_SYSTEM,
            request_kind="email_triage",
            user_id=user.id,
            agent_run_id=agent_run_id,
            session=self.session,
        )
        try:
            triage = TriageResult.model_validate(raw)
        except Exception:  # noqa: BLE001 — malformed LLM output must not kill the run
            log.warning("triage result failed validation, using fallback")
            triage = TriageResult(
                summary="Не удалось разобрать почту автоматически.",
                telegram_digest="Почта синхронизирована, но классификация не удалась. Попробуй ещё раз.",
            )

        by_external = {t.external_thread_id: t for t in threads}
        for item in triage.threads:
            thread = by_external.get(item.external_thread_id)
            if thread is None:
                continue
            thread.category = EmailCategory(item.category)
            thread.importance = item.importance
            thread.summary = item.reason or item.suggested_action
            thread.triage_status = "triaged"
            thread.metadata_ = {
                **thread.metadata_,
                "suggested_action": item.suggested_action,
                "task_candidate": item.task_candidate.model_dump(mode="json") if item.task_candidate else None,
            }
        await RealtimeEventService(self.session).emit(
            user_id=user.id,
            topics=["inbox"],
            event_type="inbox.triaged",
            payload={"thread_count": len(threads)},
        )
        return triage, threads

    # --- queries -----------------------------------------------------------

    async def inbox_summary(self, user: User, limit: int = 50) -> dict:
        counts_result = await self.session.execute(
            select(EmailThread.category, func.count())
            .where(EmailThread.user_id == user.id)
            .group_by(EmailThread.category)
        )
        counts = {category.value: 0 for category in EmailCategory}
        for category, count in counts_result.all():
            key = category.value if isinstance(category, EmailCategory) else str(category)
            counts[key] = count

        threads_result = await self.session.execute(
            select(EmailThread)
            .where(EmailThread.user_id == user.id)
            .order_by(EmailThread.last_message_at.desc().nulls_last())
            .limit(limit)
        )
        last_triage = await self.session.execute(
            select(func.max(EmailThread.updated_at)).where(
                EmailThread.user_id == user.id, EmailThread.triage_status == "triaged"
            )
        )
        return {
            "counts": counts,
            "threads": list(threads_result.scalars()),
            "last_triage_at": last_triage.scalar_one_or_none(),
        }

    async def get_thread(self, user: User, thread_id: uuid.UUID) -> EmailThread | None:
        result = await self.session.execute(
            select(EmailThread).where(EmailThread.id == thread_id, EmailThread.user_id == user.id)
        )
        return result.scalar_one_or_none()
