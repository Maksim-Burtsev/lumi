"""Static action risk policy for model-proposed work."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ActionPolicy:
    action_type: str
    risk_class: str
    approval_mode: str
    ui_mode: str
    primary_label: str
    secondary_label: str = "Отклонить"


ACTION_POLICIES: dict[str, ActionPolicy] = {
    "create_task": ActionPolicy(
        action_type="create_task",
        risk_class="write_internal",
        approval_mode="auto_or_confirm",
        ui_mode="inline_confirm",
        primary_label="Создать",
    ),
    "store_memory": ActionPolicy(
        action_type="store_memory",
        risk_class="write_internal_memory",
        approval_mode="auto",
        ui_mode="none",
        primary_label="",
    ),
    "create_automation": ActionPolicy(
        action_type="create_automation",
        risk_class="write_internal_scheduled",
        approval_mode="confirm",
        ui_mode="review_then_confirm",
        primary_label="Включить",
    ),
    "create_google_calendar_event": ActionPolicy(
        action_type="create_google_calendar_event",
        risk_class="write_external",
        approval_mode="confirm",
        ui_mode="review_then_confirm",
        primary_label="Добавить",
    ),
    "send_email": ActionPolicy(
        action_type="send_email",
        risk_class="external_communication",
        approval_mode="draft_then_confirm",
        ui_mode="review_then_confirm",
        primary_label="Отправить",
    ),
    "delete_email": ActionPolicy(
        action_type="delete_email",
        risk_class="destructive",
        approval_mode="strong_confirm",
        ui_mode="strong_confirm",
        primary_label="Удалить",
    ),
    "archive_email": ActionPolicy(
        action_type="archive_email",
        risk_class="destructive",
        approval_mode="strong_confirm",
        ui_mode="strong_confirm",
        primary_label="Архивировать",
    ),
    "disconnect_google": ActionPolicy(
        action_type="disconnect_google",
        risk_class="destructive",
        approval_mode="strong_confirm",
        ui_mode="strong_confirm",
        primary_label="Отключить",
    ),
    "disconnect_yandex": ActionPolicy(
        action_type="disconnect_yandex",
        risk_class="destructive",
        approval_mode="strong_confirm",
        ui_mode="strong_confirm",
        primary_label="Отключить",
    ),
}

UNKNOWN_ACTION_POLICY = ActionPolicy(
    action_type="unknown",
    risk_class="unknown",
    approval_mode="confirm",
    ui_mode="review_then_confirm",
    primary_label="Подтвердить",
)


def policy_for_action(action_type: str) -> ActionPolicy:
    return ACTION_POLICIES.get(action_type, UNKNOWN_ACTION_POLICY)


def policy_to_dict(policy: ActionPolicy) -> dict[str, str]:
    data = asdict(policy)
    data.pop("action_type")
    return data
