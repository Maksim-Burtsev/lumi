from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from aiogram.types import Chat
from aiogram.types import Message as TgMessage
from aiogram.types import User as TgUser

from lumi.api import deps
from lumi.bot import handlers
from lumi.config import Settings, get_settings
from lumi.db.session import session_scope
from lumi.main import app
from lumi.security import web_auth
from lumi.security.telegram_auth import sign_init_data_for_tests
from lumi.services.users import UserService

from .conftest import TEST_TELEGRAM_ID

ORIGIN = "https://app.example"
BOT_TOKEN = "123456789:TEST-TOKEN-for-tests-only"


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls: list[tuple[str, int | None, bool | None]] = []
        self.fail = False

    async def set(self, key: str, value: str, *, ex=None, nx=None):
        if self.fail:
            raise ConnectionError("redis down")
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.set_calls.append((key, ex, nx))
        return True

    async def getdel(self, key: str):
        if self.fail:
            raise ConnectionError("redis down")
        return self.values.pop(key, None)

    async def get(self, key: str):
        if self.fail:
            raise ConnectionError("redis down")
        return self.values.get(key)

    async def delete(self, key: str):
        if self.fail:
            raise ConnectionError("redis down")
        return int(self.values.pop(key, None) is not None)


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    redis = FakeRedis()

    async def fake_get_queue():
        return redis

    monkeypatch.setattr(web_auth, "get_queue", fake_get_queue)
    return redis


@pytest.fixture
async def web_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
        yield client


async def _user(telegram_id: int = TEST_TELEGRAM_ID, *, allowed: bool = False):
    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(telegram_id)
        await users.ensure_main_conversation(user)
        user.is_allowed = allowed
        return user


def _nonce(url: str) -> str:
    parsed = urlsplit(url)
    assert parsed.query == ""
    route, _, query = parsed.fragment.partition("?")
    assert route == "/web-login"
    return parse_qs(query)["nonce"][0]


async def _login(client: httpx.AsyncClient, user) -> httpx.Response:
    url = await web_auth.issue_web_login(user.id)
    return await client.post(
        "/api/auth/web/exchange",
        json={"nonce": _nonce(url)},
        headers={"Origin": ORIGIN},
    )


def _csrf(client: httpx.AsyncClient) -> str:
    value = client.cookies.get(web_auth.WEB_CSRF_COOKIE)
    assert value
    return value


def _mutation_headers(client: httpx.AsyncClient) -> dict[str, str]:
    return {"Origin": ORIGIN, web_auth.CSRF_HEADER: _csrf(client)}


def test_web_auth_configuration_requires_strong_secret_and_origin_root(monkeypatch):
    short_secret = "canary-short-secret"
    with pytest.raises(ValueError, match="at least 32") as error:
        Settings(_env_file=None, web_session_secret=short_secret)
    assert short_secret not in str(error.value)

    settings = get_settings().model_copy(update={"app_public_url": f"{ORIGIN}/nested"})
    monkeypatch.setattr(web_auth, "get_settings", lambda: settings)
    with pytest.raises(web_auth.WebAuthNotConfigured):
        web_auth.configured_web_origin()


async def test_web_login_is_single_use_and_sets_hardened_cookies(
    web_client,
    fake_redis,
):
    user = await _user()
    login_url = await web_auth.issue_web_login(user.id)
    nonce = _nonce(login_url)

    assert login_url.startswith(f"{ORIGIN}/app/#/web-login?nonce=")
    assert nonce not in login_url.split("#", 1)[0]
    assert fake_redis.set_calls[0][1:] == (web_auth.LOGIN_NONCE_TTL_SECONDS, True)
    assert nonce not in fake_redis.set_calls[0][0]

    response = await web_client.post(
        "/api/auth/web/exchange",
        json={"nonce": nonce},
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}
    assert response.headers["cache-control"] == "private, no-store"
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(value for value in cookies if value.startswith("lumi_web_session="))
    csrf_cookie = next(value for value in cookies if value.startswith("lumi_web_csrf="))
    assert all(flag in session_cookie for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/", "Max-Age="))
    assert "expires=" in session_cookie.lower()
    assert "HttpOnly" not in csrf_cookie
    assert all(flag in csrf_cookie for flag in ("Secure", "SameSite=strict", "Path=/"))
    me = await web_client.get("/api/me")
    assert me.status_code == 200
    assert me.headers["cache-control"] == "private, no-store"

    replay = await web_client.post(
        "/api/auth/web/exchange",
        json={"nonce": nonce},
        headers={"Origin": ORIGIN},
    )
    assert replay.status_code == 401
    assert replay.json() == {"error": "invalid_or_expired_login"}


async def test_exchange_rejects_bad_origin_without_consuming_nonce(web_client, fake_redis):
    user = await _user()
    nonce = _nonce(await web_auth.issue_web_login(user.id))

    rejected = await web_client.post(
        "/api/auth/web/exchange",
        json={"nonce": nonce},
        headers={"Origin": "https://evil.example"},
    )
    assert rejected.status_code == 403
    assert rejected.json() == {"error": "invalid_origin"}

    accepted = await web_client.post(
        "/api/auth/web/exchange",
        json={"nonce": nonce},
        headers={"Origin": ORIGIN},
    )
    assert accepted.status_code == 200


async def test_cookie_mutations_require_origin_and_csrf(web_client, fake_redis):
    user = await _user()
    assert (await _login(web_client, user)).status_code == 200

    missing = await web_client.patch(
        "/api/settings",
        json={"time_format": "12h"},
        headers={"Origin": ORIGIN},
    )
    assert missing.status_code == 403
    assert missing.json() == {"error": "csrf_failed"}

    mismatch = await web_client.patch(
        "/api/settings",
        json={"time_format": "12h"},
        headers={"Origin": ORIGIN, web_auth.CSRF_HEADER: "wrong"},
    )
    assert mismatch.status_code == 403
    assert mismatch.json() == {"error": "csrf_failed"}

    bad_origin = await web_client.patch(
        "/api/settings",
        json={"time_format": "12h"},
        headers={"Origin": "https://evil.example", web_auth.CSRF_HEADER: _csrf(web_client)},
    )
    assert bad_origin.status_code == 403
    assert bad_origin.json() == {"error": "invalid_origin"}

    accepted = await web_client.patch(
        "/api/settings",
        json={"time_format": "12h"},
        headers=_mutation_headers(web_client),
    )
    assert accepted.status_code == 200


async def test_logout_revokes_session_and_clears_cookies(web_client, fake_redis):
    user = await _user()
    assert (await _login(web_client, user)).status_code == 200
    old_cookie = web_client.cookies.get(web_auth.WEB_SESSION_COOKIE)

    wrong_origin = await web_client.post(
        "/api/auth/web/logout",
        headers={"Origin": "https://evil.example", web_auth.CSRF_HEADER: _csrf(web_client)},
    )
    assert wrong_origin.status_code == 403
    assert (await web_client.get("/api/me")).status_code == 200

    response = await web_client.post(
        "/api/auth/web/logout",
        headers=_mutation_headers(web_client),
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": False}
    assert response.headers["cache-control"] == "private, no-store"
    assert web_auth.WEB_SESSION_COOKIE not in web_client.cookies
    assert web_auth.WEB_CSRF_COOKIE not in web_client.cookies

    reused = await web_client.get(
        "/api/me",
        headers={"Cookie": f"{web_auth.WEB_SESSION_COOKIE}={old_cookie}"},
    )
    assert reused.status_code == 401


async def test_expired_and_tampered_sessions_are_rejected(fake_redis):
    user = await _user()
    cookie, _ = await web_auth.issue_web_session(user.id, _now=100)

    with pytest.raises(web_auth.InvalidWebSession):
        await web_auth.resolve_web_session(
            cookie,
            _now=100 + web_auth.WEB_SESSION_TTL_SECONDS + 1,
        )
    with pytest.raises(web_auth.InvalidWebSession):
        await web_auth.resolve_web_session(cookie + "tampered", _now=100)


async def test_redis_failure_fails_closed(web_client, fake_redis):
    user = await _user()
    nonce = _nonce(await web_auth.issue_web_login(user.id))
    fake_redis.fail = True

    response = await web_client.post(
        "/api/auth/web/exchange",
        json={"nonce": nonce},
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 503
    assert response.json() == {"error": "auth_unavailable"}


async def test_redis_failure_during_session_lookup_fails_closed(web_client, fake_redis):
    user = await _user()
    assert (await _login(web_client, user)).status_code == 200
    fake_redis.fail = True

    response = await web_client.get("/api/me")

    assert response.status_code == 503
    assert response.json() == {"error": "auth_unavailable"}


async def test_web_sessions_are_cross_user_isolated(fake_redis):
    owner = await _user()
    invited = await _user(888001, allowed=True)
    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url=ORIGIN) as owner_client,
        httpx.AsyncClient(transport=transport, base_url=ORIGIN) as invited_client,
    ):
        assert (await _login(owner_client, owner)).status_code == 200
        assert (await _login(invited_client, invited)).status_code == 200
        created = await owner_client.post(
            "/api/tasks",
            json={"title": "Owner only"},
            headers=_mutation_headers(owner_client),
        )
        assert created.status_code == 201

        invited_tasks = await invited_client.get("/api/tasks")
        assert invited_tasks.status_code == 200
        assert invited_tasks.json()["items"] == []


async def test_revoked_user_cannot_exchange_or_reuse_session(fake_redis):
    invited = await _user(888002, allowed=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
        url = await web_auth.issue_web_login(invited.id)
        async with session_scope() as session:
            db_user = await UserService(session).get_by_telegram_id(invited.telegram_user_id)
            assert db_user is not None
            db_user.is_allowed = False
        rejected = await client.post(
            "/api/auth/web/exchange",
            json={"nonce": _nonce(url)},
            headers={"Origin": ORIGIN},
        )
        assert rejected.status_code == 401

        async with session_scope() as session:
            db_user = await UserService(session).get_by_telegram_id(invited.telegram_user_id)
            assert db_user is not None
            db_user.is_allowed = True
        assert (await _login(client, invited)).status_code == 200
        async with session_scope() as session:
            db_user = await UserService(session).get_by_telegram_id(invited.telegram_user_id)
            assert db_user is not None
            db_user.is_allowed = False
        assert (await client.get("/api/me")).status_code == 401


async def test_init_data_precedes_cookie_and_needs_no_csrf(web_client, fake_redis):
    await _user()
    params = {
        "auth_date": str(int(time.time())),
        "query_id": "AAE1",
        "user": json.dumps({"id": TEST_TELEGRAM_ID, "first_name": "Test"}),
    }
    init_data = sign_init_data_for_tests(params, BOT_TOKEN)

    response = await web_client.patch(
        "/api/settings",
        json={"time_format": "24h"},
        headers={
            "X-Telegram-Init-Data": init_data,
            "Cookie": f"{web_auth.WEB_SESSION_COOKIE}=invalid",
        },
    )
    assert response.status_code == 200


async def test_invalid_cookie_does_not_fall_back_to_local_dev_auth(
    web_client,
    fake_redis,
    monkeypatch,
):
    await _user()
    settings = get_settings().model_copy(update={
        "app_env": "local",
        "dev_auth_enabled": True,
        "dev_auth_telegram_user_id": TEST_TELEGRAM_ID,
    })
    monkeypatch.setattr(deps, "get_settings", lambda: settings)

    local = await web_client.get("/api/me")
    assert local.status_code == 200
    invalid = await web_client.get(
        "/api/me",
        headers={"Cookie": f"{web_auth.WEB_SESSION_COOKIE}=invalid"},
    )
    assert invalid.status_code == 401


class FakeTelegramMessage:
    def __init__(self, *, user_id: int = TEST_TELEGRAM_ID, chat_type: str = "private") -> None:
        self.chat = SimpleNamespace(id=user_id, type=chat_type)
        self.from_user = SimpleNamespace(
            id=user_id,
            username="tester",
            first_name="Test",
            last_name="User",
            language_code="en",
        )
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, **kwargs):
        self.answers.append((text, kwargs.get("reply_markup")))


async def test_web_command_issues_fragment_link_for_allowed_user(fake_redis):
    allowed = FakeTelegramMessage()
    await handlers.cmd_web(allowed)

    assert len(allowed.answers) == 1
    markup = allowed.answers[0][1]
    assert markup is not None
    url = markup.inline_keyboard[0][0].url
    assert url.startswith(f"{ORIGIN}/app/#/web-login?nonce=")
    assert urlsplit(url).query == ""

    outsider = FakeTelegramMessage(user_id=999001)
    await handlers.cmd_web(outsider)
    assert outsider.answers == []


async def test_web_command_access_check_rejects_group_even_for_owner():
    message = TgMessage(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=TEST_TELEGRAM_ID, type="group", title="Test"),
        from_user=TgUser(id=TEST_TELEGRAM_ID, is_bot=False, first_name="Test"),
    )

    assert await handlers._check_allowed(message) is False
