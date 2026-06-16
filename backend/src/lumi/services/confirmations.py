"""Pending confirmations: risky/low-confidence actions wait for an explicit yes."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import ConfirmationStatus, PendingConfirmation, User
from lumi.services.audit import AuditService
from lumi.services.realtime import RealtimeEventService
from lumi.utils.time import utc_now

DEFAULT_TTL = timedelta(hours=48)


class ConfirmationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    async def create(
        self,
        user: User,
        *,
        action_type: str,
        action_payload: dict[str, Any],
        prompt: str,
    ) -> PendingConfirmation:
        confirmation = PendingConfirmation(
            user_id=user.id,
            action_type=action_type,
            action_payload=action_payload,
            prompt=prompt,
            status=ConfirmationStatus.PENDING,
            expires_at=utc_now() + DEFAULT_TTL,
        )
        self.session.add(confirmation)
        await self.session.flush()
        await self.audit.log(user_id=user.id, actor="agent", entity_type="confirmation",
                             entity_id=confirmation.id, action="created",
                             details={"action_type": action_type})
        await self._emit_confirmation_changed(confirmation, "confirmation.created")
        return confirmation

    async def get(self, user: User, confirmation_id: uuid.UUID) -> PendingConfirmation | None:
        result = await self.session.execute(
            select(PendingConfirmation).where(
                PendingConfirmation.id == confirmation_id,
                PendingConfirmation.user_id == user.id,
            )
        )
        return result.scalar_one_or_none()

    async def list_pending(self, user: User, limit: int = 20) -> list[PendingConfirmation]:
        result = await self.session.execute(
            select(PendingConfirmation)
            .where(
                PendingConfirmation.user_id == user.id,
                PendingConfirmation.status == ConfirmationStatus.PENDING,
            )
            .order_by(PendingConfirmation.created_at.desc())
            .limit(limit)
        )
        confirmations = list(result.scalars())
        # Lazily expire stale ones.
        now = utc_now()
        alive: list[PendingConfirmation] = []
        for c in confirmations:
            if c.expires_at and c.expires_at < now:
                c.status = ConfirmationStatus.EXPIRED
                await self._emit_confirmation_changed(c, "confirmation.expired")
            else:
                alive.append(c)
        return alive

    async def decide(
        self, user: User, confirmation: PendingConfirmation, *, accept: bool
    ) -> PendingConfirmation:
        if confirmation.status != ConfirmationStatus.PENDING:
            return confirmation
        if confirmation.expires_at and confirmation.expires_at < utc_now():
            confirmation.status = ConfirmationStatus.EXPIRED
            return confirmation
        confirmation.status = ConfirmationStatus.ACCEPTED if accept else ConfirmationStatus.REJECTED
        confirmation.decided_at = utc_now()
        # Learning signal: accept/reject stats per action type feed future
        # threshold tuning (the agent should propose less of what gets rejected).
        stats = dict((user.settings or {}).get("confirm_stats", {}))
        entry = dict(stats.get(confirmation.action_type, {"accepted": 0, "rejected": 0}))
        entry["accepted" if accept else "rejected"] += 1
        stats[confirmation.action_type] = entry
        user.settings = {**(user.settings or {}), "confirm_stats": stats}
        await self.audit.log(
            user_id=user.id, actor="user", entity_type="confirmation",
            entity_id=confirmation.id,
            action="accepted" if accept else "rejected",
            details={"action_type": confirmation.action_type},
        )
        await self._emit_confirmation_changed(
            confirmation,
            "confirmation.accepted" if accept else "confirmation.rejected",
        )
        return confirmation

    async def _emit_confirmation_changed(
        self, confirmation: PendingConfirmation, event_type: str
    ) -> None:
        await RealtimeEventService(self.session).emit(
            user_id=confirmation.user_id,
            topics=["confirmations"],
            event_type=event_type,
            payload={
                "confirmation_id": str(confirmation.id),
                "action_type": confirmation.action_type,
            },
        )
