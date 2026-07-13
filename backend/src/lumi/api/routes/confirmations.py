"""Mini App API for pending confirmations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.api.serializers import confirmation_to_dict
from lumi.db.models import ConfirmationStatus, User
from lumi.i18n import normalize_app_locale
from lumi.services.confirmation_executor import (
    REMOVED_CONFIRMATION_ACTIONS,
    ConfirmationExecutor,
)
from lumi.services.confirmations import ConfirmationService

router = APIRouter()


async def _get_pending_confirmation(
    confirmation_id: str,
    user: User,
    session: AsyncSession,
):
    try:
        parsed = uuid.UUID(confirmation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc

    confirmation = await ConfirmationService(session).get(user, parsed)
    if confirmation is None:
        raise HTTPException(status_code=404, detail="not_found")
    if confirmation.status != ConfirmationStatus.PENDING:
        raise HTTPException(status_code=409, detail="already_decided")
    return confirmation


@router.post("/confirmations/{confirmation_id}/accept")
async def accept_confirmation(
    confirmation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    locale = normalize_app_locale(user.locale)
    service = ConfirmationService(session)
    confirmation = await _get_pending_confirmation(confirmation_id, user, session)
    confirmation = await service.decide(user, confirmation, accept=True)
    if confirmation.status == ConfirmationStatus.EXPIRED:
        return {
            "confirmation": confirmation_to_dict(confirmation, locale=locale),
            "result_text": _text(locale, "This suggestion has expired.", "Это предложение уже истекло."),
            "executed": False,
        }
    if confirmation.action_type in REMOVED_CONFIRMATION_ACTIONS:
        return {
            "confirmation": confirmation_to_dict(confirmation, locale=locale),
            "result_text": _text(
                locale,
                "This action is no longer available in Lumi's productivity scope.",
                "Это действие больше не входит в продуктивный контур Lumi.",
            ),
            "executed": False,
        }

    result_text = await ConfirmationExecutor(session).execute(user, confirmation)
    return {
        "confirmation": confirmation_to_dict(confirmation, locale=locale),
        "result_text": result_text,
        "executed": True,
    }


@router.post("/confirmations/{confirmation_id}/reject")
async def reject_confirmation(
    confirmation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    locale = normalize_app_locale(user.locale)
    service = ConfirmationService(session)
    confirmation = await _get_pending_confirmation(confirmation_id, user, session)
    confirmation = await service.decide(user, confirmation, accept=False)
    result_text = (
        _text(locale, "This suggestion has expired.", "Это предложение уже истекло.")
        if confirmation.status == ConfirmationStatus.EXPIRED
        else _text(locale, "Ok, I won't do it.", "Ок, не делаю.")
    )
    return {
        "confirmation": confirmation_to_dict(confirmation, locale=locale),
        "result_text": result_text,
        "executed": False,
    }


def _text(locale: str, en: str, ru: str) -> str:
    return en if locale == "en" else ru
