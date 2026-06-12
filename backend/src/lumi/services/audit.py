"""Audit trail for every meaningful state change."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import AuditLog


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(
        self,
        *,
        user_id: uuid.UUID | None,
        actor: str,  # user / agent / system
        entity_type: str,
        action: str,
        entity_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                user_id=user_id,
                actor=actor,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                details=details or {},
            )
        )
