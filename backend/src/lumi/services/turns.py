"""Durable Telegram chat intake and per-user assistant turn queue."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.config import Settings, get_settings
from lumi.db.models import AssistantTurn, TelegramUpdate, User
from lumi.services.users import UserService
from lumi.utils.time import utc_now


@dataclass(slots=True)
class TurnIntakeResult:
    turn: AssistantTurn | None
    duplicate_update: bool
    should_enqueue: bool
    enqueue_at: datetime | None
    created_turn: bool = False


@dataclass(slots=True)
class TurnAcquireResult:
    status: str
    turn: AssistantTurn | None = None
    enqueue_at: datetime | None = None


class TelegramIntakeService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        now: Callable[[], datetime] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self._now = now or utc_now
        self.settings = settings or get_settings()

    async def ingest_chat_message(
        self,
        *,
        update_id: int | None,
        telegram_user_id: int,
        telegram_chat_id: int,
        telegram_message_id: int,
        text: str,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
        image_metadata: dict[str, Any] | None = None,
        ignored_attachments: list[dict[str, Any]] | None = None,
        status_message_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> TurnIntakeResult:
        now = self._now()
        if update_id is not None:
            inserted = await self.session.execute(
                insert(TelegramUpdate)
                .values(
                    update_id=update_id,
                    telegram_user_id=telegram_user_id,
                    telegram_chat_id=telegram_chat_id,
                    telegram_message_id=telegram_message_id,
                    payload=payload or {},
                )
                .on_conflict_do_nothing(index_elements=[TelegramUpdate.update_id])
                .returning(TelegramUpdate.id)
            )
            if inserted.scalar_one_or_none() is None:
                return TurnIntakeResult(
                    turn=None,
                    duplicate_update=True,
                    should_enqueue=False,
                    enqueue_at=None,
                    created_turn=False,
                )

        users = UserService(self.session)
        user = await users.ensure_user(
            telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
        )
        conversation = await users.ensure_main_conversation(user)

        # Serialize sequence assignment and same-window append for this user.
        await self.session.execute(select(User).where(User.id == user.id).with_for_update())

        pending_count = await self._pending_turn_count(user.id)
        if pending_count >= self.settings.telegram_max_queue_per_user:
            return TurnIntakeResult(
                turn=None,
                duplicate_update=False,
                should_enqueue=False,
                enqueue_at=None,
                created_turn=False,
            )

        debounce = timedelta(milliseconds=self.settings.telegram_chat_debounce_ms)
        deadline = now + debounce
        turn = await self._current_collecting_text_turn(user.id, now, image_metadata=image_metadata)
        created_turn = turn is None
        if turn is None:
            sequence_no = await self._next_sequence_no(user.id)
            turn = AssistantTurn(
                user_id=user.id,
                conversation_id=conversation.id,
                sequence_no=sequence_no,
                input_text=self._stored_text(text, image_metadata),
                telegram_chat_id=telegram_chat_id,
                primary_message_id=telegram_message_id,
                source_update_ids=[update_id] if update_id is not None else [],
                source_message_ids=[telegram_message_id],
                payload=self._turn_payload(
                    text=text,
                    image_metadata=image_metadata,
                    ignored_attachments=ignored_attachments,
                    payload=payload,
                ),
                status_message_id=status_message_id,
                debounce_deadline_at=deadline,
            )
            self.session.add(turn)
            await self.session.flush()
        else:
            turn.input_text = self._append_text(turn.input_text, self._stored_text(text, image_metadata))
            turn.primary_message_id = turn.primary_message_id or telegram_message_id
            turn.source_update_ids = self._append_unique(turn.source_update_ids, update_id)
            turn.source_message_ids = self._append_unique(turn.source_message_ids, telegram_message_id)
            turn.payload = self._merged_payload(
                turn.payload,
                text=text,
                image_metadata=image_metadata,
                ignored_attachments=ignored_attachments,
                payload=payload,
            )
            turn.debounce_deadline_at = deadline

        return TurnIntakeResult(
            turn=turn,
            duplicate_update=False,
            should_enqueue=True,
            enqueue_at=turn.debounce_deadline_at,
            created_turn=created_turn,
        )

    async def _pending_turn_count(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(AssistantTurn)
            .where(AssistantTurn.user_id == user_id, AssistantTurn.status.in_(("collecting", "queued", "running")))
        )
        return int(result.scalar_one())

    async def _current_collecting_text_turn(
        self,
        user_id: uuid.UUID,
        now: datetime,
        *,
        image_metadata: dict[str, Any] | None,
    ) -> AssistantTurn | None:
        if image_metadata:
            return None
        result = await self.session.execute(
            select(AssistantTurn)
            .where(
                AssistantTurn.user_id == user_id,
                AssistantTurn.status == "collecting",
                AssistantTurn.debounce_deadline_at >= now,
            )
            .order_by(AssistantTurn.sequence_no.desc())
            .limit(1)
            .with_for_update()
        )
        turn = result.scalar_one_or_none()
        if turn is not None and (turn.payload or {}).get("image"):
            return None
        return turn

    async def _next_sequence_no(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.max(AssistantTurn.sequence_no)).where(AssistantTurn.user_id == user_id)
        )
        return int(result.scalar_one() or 0) + 1

    def _stored_text(self, text: str, image_metadata: dict[str, Any] | None) -> str:
        stripped = text.strip()
        return stripped or ("[image]" if image_metadata else "")

    def _turn_payload(
        self,
        *,
        text: str,
        image_metadata: dict[str, Any] | None,
        ignored_attachments: list[dict[str, Any]] | None,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        data = dict(payload or {})
        data["text"] = text
        if image_metadata:
            data["image"] = image_metadata
        if ignored_attachments:
            data["ignored_attachments"] = list(ignored_attachments)
        data["messages"] = [{"text": text, "image": image_metadata}]
        return data

    def _merged_payload(
        self,
        existing: dict[str, Any],
        *,
        text: str,
        image_metadata: dict[str, Any] | None,
        ignored_attachments: list[dict[str, Any]] | None,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = {**(existing or {}), **(payload or {})}
        merged["text"] = self._append_text(str((existing or {}).get("text") or ""), text)
        if image_metadata:
            merged["image"] = image_metadata
        if ignored_attachments:
            merged["ignored_attachments"] = [
                *((existing or {}).get("ignored_attachments") or []),
                *ignored_attachments,
            ]
        merged["messages"] = [
            *((existing or {}).get("messages") or []),
            {"text": text, "image": image_metadata},
        ]
        return merged

    def _append_text(self, current: str, new: str) -> str:
        current = current.strip()
        new = new.strip()
        if not current:
            return new
        if not new:
            return current
        return f"{current}\n\n{new}"

    def _append_unique(self, values: list, value: Any | None) -> list:
        if value is None or value in values:
            return list(values)
        return [*values, value]


class TurnService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self._now = now or utc_now

    async def acquire_turn(self, turn_id: uuid.UUID, *, lock_seconds: int) -> TurnAcquireResult:
        now = self._now()
        turn_user_id = await self._turn_user_id(turn_id)
        if turn_user_id is None:
            return TurnAcquireResult(status="missing")
        await self.session.execute(select(User).where(User.id == turn_user_id).with_for_update())
        turn = await self._get_for_update(turn_id)
        if turn is None:
            return TurnAcquireResult(status="missing")
        if turn.status == "running" and turn.locked_until and turn.locked_until > now:
            return TurnAcquireResult(status="already_running")
        if turn.status == "running":
            turn.status = "failed"
            turn.finished_at = now
            turn.locked_until = None
            turn.error_message = "turn lock expired before completion"
            return TurnAcquireResult(status="stale")
        if turn.status in {"completed", "failed", "cancelled"}:
            return TurnAcquireResult(status=turn.status)
        if turn.debounce_deadline_at > now:
            return TurnAcquireResult(status="deferred", enqueue_at=turn.debounce_deadline_at)

        running = await self.session.execute(
            select(AssistantTurn.id)
            .where(
                AssistantTurn.user_id == turn.user_id,
                AssistantTurn.id != turn.id,
                AssistantTurn.status == "running",
                AssistantTurn.locked_until > now,
            )
            .limit(1)
        )
        if running.scalar_one_or_none() is not None:
            return TurnAcquireResult(status="locked")

        oldest = await self._oldest_runnable_turn(turn.user_id, now)
        if oldest is None or oldest.id != turn.id:
            return TurnAcquireResult(status="not_ready", turn=oldest)

        turn.status = "running"
        turn.started_at = turn.started_at or now
        turn.locked_until = now + timedelta(seconds=lock_seconds)
        return TurnAcquireResult(status="acquired", turn=turn)

    async def set_status_message(self, turn_id: uuid.UUID, status_message_id: int) -> None:
        turn = await self._get_for_update(turn_id)
        if turn is not None and turn.status_message_id is None:
            turn.status_message_id = status_message_id

    async def complete_turn(self, turn_id: uuid.UUID) -> AssistantTurn | None:
        now = self._now()
        turn = await self._get_for_update(turn_id)
        if turn is None:
            return None
        turn.status = "completed"
        turn.finished_at = now
        turn.locked_until = None
        return await self._next_turn(turn.user_id)

    async def fail_turn(self, turn_id: uuid.UUID, error: str) -> AssistantTurn | None:
        now = self._now()
        turn = await self._get_for_update(turn_id)
        if turn is None:
            return None
        user_id = turn.user_id
        turn.retry_count += 1
        turn.error_message = error[:1000]
        turn.locked_until = None
        turn.status = "failed"
        turn.finished_at = now
        return await self._next_turn(user_id)

    async def retry_turn(self, turn_id: uuid.UUID, error: str, *, delay_seconds: int) -> AssistantTurn | None:
        now = self._now()
        turn = await self._get_for_update(turn_id)
        if turn is None:
            return None
        turn.retry_count += 1
        turn.error_message = error[:1000]
        turn.locked_until = None
        turn.status = "queued"
        turn.debounce_deadline_at = now + timedelta(seconds=delay_seconds)
        return turn

    async def find_due_turns(self, *, limit: int = 100) -> list[AssistantTurn]:
        now = self._now()
        result = await self.session.execute(
            select(AssistantTurn)
            .where(
                AssistantTurn.status.in_(("collecting", "queued")),
                AssistantTurn.debounce_deadline_at <= now,
            )
            .order_by(AssistantTurn.created_at)
            .limit(limit)
        )
        return list(result.scalars())

    async def reserve_due_turns(self, *, limit: int = 100, lease_seconds: int = 60) -> list[AssistantTurn]:
        now = self._now()
        result = await self.session.execute(
            select(AssistantTurn)
            .where(
                or_(
                    and_(
                        AssistantTurn.status.in_(("collecting", "queued")),
                        AssistantTurn.debounce_deadline_at <= now,
                        (AssistantTurn.locked_until.is_(None) | (AssistantTurn.locked_until <= now)),
                    ),
                    and_(
                        AssistantTurn.status == "running",
                        AssistantTurn.locked_until.is_not(None),
                        AssistantTurn.locked_until <= now,
                    ),
                )
            )
            .order_by(AssistantTurn.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        turns = list(result.scalars())
        lease_until = now + timedelta(seconds=lease_seconds)
        for turn in turns:
            if turn.status == "running":
                turn.error_message = "turn lock expired; queued for recovery"
                turn.debounce_deadline_at = now
            turn.status = "queued"
            turn.locked_until = lease_until
        return turns

    async def _get_for_update(self, turn_id: uuid.UUID) -> AssistantTurn | None:
        result = await self.session.execute(
            select(AssistantTurn).where(AssistantTurn.id == turn_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def _turn_user_id(self, turn_id: uuid.UUID) -> uuid.UUID | None:
        result = await self.session.execute(
            select(AssistantTurn.user_id).where(AssistantTurn.id == turn_id)
        )
        return result.scalar_one_or_none()

    async def _oldest_runnable_turn(self, user_id: uuid.UUID, now: datetime) -> AssistantTurn | None:
        result = await self.session.execute(
            select(AssistantTurn)
            .where(
                AssistantTurn.user_id == user_id,
                AssistantTurn.status.in_(("collecting", "queued")),
                AssistantTurn.debounce_deadline_at <= now,
            )
            .order_by(AssistantTurn.sequence_no)
            .limit(1)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _next_turn(self, user_id: uuid.UUID) -> AssistantTurn | None:
        result = await self.session.execute(
            select(AssistantTurn)
            .where(
                AssistantTurn.user_id == user_id,
                AssistantTurn.status.in_(("collecting", "queued")),
            )
            .order_by(AssistantTurn.sequence_no)
            .limit(1)
        )
        return result.scalar_one_or_none()
