from __future__ import annotations

from typing import Any


def normalize_email(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower().startswith("mailto:"):
        text = text[7:]
    return text or None


def compact_person(value: dict[str, Any] | None) -> dict[str, str] | None:
    if not value:
        return None
    name = str(value.get("displayName") or value.get("name") or "").strip()
    email = normalize_email(value.get("email"))
    if not name and not email:
        return None
    return {key: val for key, val in {"name": name or None, "email": email}.items() if val}


def normalize_response_status(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    mapping = {
        "ACCEPTED": "accepted",
        "DECLINED": "declined",
        "TENTATIVE": "tentative",
        "NEEDS-ACTION": "needsAction",
        "NEEDSACTION": "needsAction",
        "needsaction": "needsAction",
    }
    return mapping.get(raw, mapping.get(raw.upper(), raw))
