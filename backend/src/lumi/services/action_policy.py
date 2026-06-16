"""Static action risk policy for model-proposed work."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from lumi.i18n import normalize_app_locale


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
    "bulk_update_tasks": ActionPolicy(
        action_type="bulk_update_tasks",
        risk_class="write_internal",
        approval_mode="confirm",
        ui_mode="inline_confirm",
        primary_label="Обновить",
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

_LOCALIZED_LABELS: dict[str, dict[str, tuple[str, str]]] = {
    "create_task": {"en": ("Create", "Dismiss"), "ru": ("Создать", "Отклонить")},
    "bulk_update_tasks": {"en": ("Update", "Dismiss"), "ru": ("Обновить", "Отклонить")},
    "store_memory": {"en": ("Remember", "Dismiss"), "ru": ("", "Отклонить")},
    "create_automation": {"en": ("Enable", "Dismiss"), "ru": ("Включить", "Отклонить")},
    "create_google_calendar_event": {"en": ("Add", "Dismiss"), "ru": ("Добавить", "Отклонить")},
    "send_email": {"en": ("Send", "Dismiss"), "ru": ("Отправить", "Отклонить")},
    "delete_email": {"en": ("Delete", "Dismiss"), "ru": ("Удалить", "Отклонить")},
    "archive_email": {"en": ("Archive", "Dismiss"), "ru": ("Архивировать", "Отклонить")},
    "disconnect_google": {"en": ("Disconnect", "Dismiss"), "ru": ("Отключить", "Отклонить")},
    "disconnect_yandex": {"en": ("Disconnect", "Dismiss"), "ru": ("Отключить", "Отклонить")},
    "unknown": {"en": ("Confirm", "Dismiss"), "ru": ("Подтвердить", "Отклонить")},
}


def policy_for_action(action_type: str) -> ActionPolicy:
    return ACTION_POLICIES.get(action_type, UNKNOWN_ACTION_POLICY)


def policy_to_dict(policy: ActionPolicy, *, locale: str | None = None) -> dict[str, str]:
    data = asdict(policy)
    data.pop("action_type")
    localized = _LOCALIZED_LABELS.get(policy.action_type, _LOCALIZED_LABELS["unknown"])[
        normalize_app_locale(locale)
    ]
    data["primary_label"] = localized[0]
    data["secondary_label"] = localized[1]
    return data
