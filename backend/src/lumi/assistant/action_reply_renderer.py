"""MiniMax-backed wording for completed assistant actions."""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.i18n import ensure_language_settings, normalize_reply_language
from lumi.llm.base import LLMMessage
from lumi.llm.gateway import LLMGateway
from lumi.logging import get_logger

log = get_logger(__name__)


class ActionOutcome(BaseModel):
    """Backend-owned action facts safe to show to the user."""

    action_type: str
    status: Literal["completed", "requires_confirmation", "skipped", "failed"]
    fallback_text: str
    title: str | None = None
    project: str | None = None
    count: int | None = None
    due_at_local: str | None = None
    reminder_at_local: str | None = None
    error_code: str | None = None
    reason: str | None = None
    button_keys: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action_type", "fallback_text", "title", "project", "error_code", "reason")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(str(value).split()).strip()
        if not value:
            return None
        return value[:1000]

    @field_validator("button_keys")
    @classmethod
    def clean_button_keys(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            key = " ".join(str(item).split()).strip()
            if key and key not in cleaned:
                cleaned.append(key[:80])
        return cleaned[:20]


class RenderedActionReply(BaseModel):
    message: str
    button_labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("empty message")
        return value[:2000]

    @field_validator("button_labels")
    @classmethod
    def clean_button_labels(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for key, label in value.items():
            key = " ".join(str(key).split()).strip()
            label = " ".join(str(label).split()).strip()
            if key and label:
                cleaned[key[:80]] = label[:80]
        return cleaned


ACTION_REPLY_RENDERER_SYSTEM = """You write the final user-visible reply after Lumi backend actions.
Return valid JSON only.

Rules:
- Backend action_outcomes are the source of truth. Do not invent actions, counts, titles, projects, dates, or failures.
- Reply in target_language.
- Preserve task titles, project names, tags, and user-provided quoted text verbatim.
- Keep the message short and natural for chat.
- If an action requires confirmation, ask for confirmation without claiming it was completed.
- You may localize button labels only for keys present in button_keys. Never change callback data.
- Do not mention backend, tools, JSON, renderer, prompts, or policies."""


ACTION_REPLY_SCHEMA_HINT = {
    "message": "localized user-visible reply; required",
    "button_labels": {
        "button_key": "localized label for an existing button key; optional",
    },
}


class ActionReplyRenderer:
    def __init__(self, llm: LLMGateway) -> None:
        self.llm = llm

    async def render(
        self,
        *,
        user,
        latest_user_message: str,
        planner_language: str | None,
        outcomes: list[ActionOutcome],
        run_id: uuid.UUID,
        session: AsyncSession,
    ) -> RenderedActionReply | None:
        if not outcomes:
            return None

        language_settings = ensure_language_settings(user.settings)
        target_language = self._target_language(
            user_locale=user.locale,
            planner_language=planner_language,
            language_settings=language_settings,
        )
        payload = {
            "reply_language_mode": language_settings["reply_language_mode"],
            "target_language": target_language,
            "latest_user_message": latest_user_message,
            "action_outcomes": [outcome.model_dump(mode="json") for outcome in outcomes],
        }
        prompt = (
            f"reply_language_mode: {language_settings['reply_language_mode']}\n"
            f"target_language: {target_language}\n"
            "payload_json:\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True)
        )
        try:
            data = await self.llm.complete_json(
                messages=[LLMMessage(role="user", content=prompt)],
                system=ACTION_REPLY_RENDERER_SYSTEM,
                json_schema_hint=ACTION_REPLY_SCHEMA_HINT,
                request_kind="action_reply_renderer",
                user_id=user.id,
                agent_run_id=run_id,
                session=session,
                temperature=0.1,
                max_tokens=800,
            )
            rendered = RenderedActionReply.model_validate(data)
        except Exception as exc:  # noqa: BLE001 - fallback text is the reliability boundary
            log.warning(
                "action reply renderer failed",
                fields={
                    "user_id": str(user.id),
                    "agent_run_id": str(run_id),
                    "error": str(exc)[:500],
                },
            )
            return None
        allowed_keys = {key for outcome in outcomes for key in outcome.button_keys}
        if allowed_keys:
            labels = {
                key: label
                for key, label in rendered.button_labels.items()
                if key in allowed_keys
            }
            rendered = rendered.model_copy(update={"button_labels": labels})
        else:
            rendered = rendered.model_copy(update={"button_labels": {}})
        return rendered

    @classmethod
    def render_deterministic(
        cls,
        *,
        user,
        planner_language: str | None,
        outcomes: list[ActionOutcome],
    ) -> RenderedActionReply | None:
        """Render action facts without a second model call.

        Command-core action flows already spent their single model call choosing
        a validated command. Backend outcomes are therefore rendered directly.
        """

        if not outcomes:
            return None
        language_settings = ensure_language_settings(user.settings)
        language = cls._target_language(
            user_locale=user.locale,
            planner_language=planner_language,
            language_settings=language_settings,
        )
        russian = language.startswith("ru")
        messages: list[str] = []
        button_labels: dict[str, str] = {}
        for outcome in outcomes:
            if outcome.action_type == "create_task" and outcome.title:
                if outcome.status == "completed":
                    message = (
                        f"Создана задача: «{outcome.title}»"
                        if russian
                        else f"Created task: “{outcome.title}”"
                    )
                    if outcome.project:
                        message += (
                            f" в проекте {outcome.project}"
                            if russian
                            else f" in project {outcome.project}"
                        )
                    messages.append(message)
                    continue
                if outcome.status == "requires_confirmation":
                    message = (
                        f"Предложена задача «{outcome.title}»"
                        if russian
                        else f"Proposed task “{outcome.title}”"
                    )
                    if outcome.project:
                        message += (
                            f" в проекте {outcome.project}"
                            if russian
                            else f" in project {outcome.project}"
                        )
                    message += " — ждёт подтверждения" if russian else " — waiting for confirmation"
                    messages.append(message)
                    continue
            messages.append(outcome.fallback_text)

        available_keys = {key for outcome in outcomes for key in outcome.button_keys}
        labels = (
            {
                "task_done": "✓ Выполнено",
                "task_snooze": "⏰ Отложить",
                "confirm": "✓ Подтвердить",
                "reject": "✗ Не надо",
            }
            if russian
            else {
                "task_done": "✓ Done",
                "task_snooze": "⏰ Snooze",
                "confirm": "✓ Confirm",
                "reject": "✗ No",
            }
        )
        button_labels = {key: label for key, label in labels.items() if key in available_keys}
        if len(messages) == 1:
            message = messages[0]
        else:
            heading = "Готово:" if russian else "Done:"
            message = heading + "\n" + "\n".join(f"• {item}" for item in messages)
        return RenderedActionReply(message=message, button_labels=button_labels)

    @staticmethod
    def _target_language(
        *,
        user_locale: str,
        planner_language: str | None,
        language_settings: dict,
    ) -> str:
        return normalize_reply_language(planner_language)
