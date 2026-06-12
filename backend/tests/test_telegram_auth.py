import json
import time

import pytest

from lumi.security.telegram_auth import (
    InitDataError,
    sign_init_data_for_tests,
    validate_init_data,
)

BOT_TOKEN = "123456789:TEST-TOKEN-for-tests-only"


def _params(user_id: int = 777000, auth_date: int | None = None) -> dict[str, str]:
    return {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAE1",
        "user": json.dumps({"id": user_id, "first_name": "Тест", "username": "tester"}),
    }


def test_valid_init_data_passes():
    init_data = sign_init_data_for_tests(_params(), BOT_TOKEN)
    user = validate_init_data(init_data, BOT_TOKEN)
    assert user.id == 777000
    assert user.username == "tester"


def test_tampered_hash_rejected():
    init_data = sign_init_data_for_tests(_params(), BOT_TOKEN)
    tampered = init_data.replace("hash=", "hash=00")
    with pytest.raises(InitDataError):
        validate_init_data(tampered, BOT_TOKEN)


def test_wrong_bot_token_rejected():
    init_data = sign_init_data_for_tests(_params(), "999:OTHER")
    with pytest.raises(InitDataError):
        validate_init_data(init_data, BOT_TOKEN)


def test_expired_auth_date_rejected():
    old = int(time.time()) - 100_000
    init_data = sign_init_data_for_tests(_params(auth_date=old), BOT_TOKEN)
    with pytest.raises(InitDataError, match="expired"):
        validate_init_data(init_data, BOT_TOKEN)


def test_missing_init_data_rejected():
    with pytest.raises(InitDataError):
        validate_init_data("", BOT_TOKEN)


def test_no_user_rejected():
    params = {"auth_date": str(int(time.time()))}
    init_data = sign_init_data_for_tests(params, BOT_TOKEN)
    with pytest.raises(InitDataError):
        validate_init_data(init_data, BOT_TOKEN)
