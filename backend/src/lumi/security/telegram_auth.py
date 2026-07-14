"""Telegram Mini App initData validation (HMAC per Telegram spec)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

INIT_DATA_MAX_AGE_SECONDS = 24 * 3600
INIT_DATA_CLOCK_SKEW_SECONDS = 30


class InitDataError(Exception):
    pass


@dataclass(slots=True)
class TelegramWebAppUser:
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = INIT_DATA_MAX_AGE_SECONDS,
    _now: float | None = None,
) -> TelegramWebAppUser:
    """Validate raw WebApp initData and return the authenticated Telegram user.

    Implements https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app:
    secret_key = HMAC_SHA256(key="WebAppData", data=bot_token)
    hash = HMAC_SHA256(key=secret_key, data=data_check_string)
    """
    if not init_data:
        raise InitDataError("missing initData")
    if not bot_token:
        raise InitDataError("bot token not configured")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True)
    except ValueError as exc:
        raise InitDataError("malformed initData") from exc

    data = dict(pairs)
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise InitDataError("initData has no hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise InitDataError("initData signature mismatch")

    auth_date = data.get("auth_date")
    if not auth_date:
        raise InitDataError("initData has no auth_date")
    now = _now if _now is not None else time.time()
    try:
        age = now - int(auth_date)
    except ValueError as exc:
        raise InitDataError("bad auth_date") from exc
    if age < -INIT_DATA_CLOCK_SKEW_SECONDS:
        raise InitDataError("initData auth_date is in the future")
    if age > max_age_seconds:
        raise InitDataError("initData expired")

    user_raw = data.get("user")
    if not user_raw:
        raise InitDataError("initData has no user")
    try:
        user_obj = json.loads(user_raw)
        return TelegramWebAppUser(
            id=int(user_obj["id"]),
            first_name=user_obj.get("first_name"),
            last_name=user_obj.get("last_name"),
            username=user_obj.get("username"),
            language_code=user_obj.get("language_code"),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise InitDataError("bad user payload in initData") from exc


def sign_init_data_for_tests(params: dict[str, str], bot_token: str) -> str:
    """Build a correctly signed initData string — used by the test suite."""
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    from urllib.parse import urlencode

    return urlencode({**params, "hash": computed})
