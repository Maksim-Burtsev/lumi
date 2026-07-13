from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

from lumi.db.models import AgentRunType
from lumi.db.session import session_scope
from lumi.services import notifier
from lumi.services.runs import RunService
from lumi.utils.time import local_to_utc
from lumi.worker import jobs


async def _set_locale(user, locale: str) -> None:
    async with session_scope() as session:
        db_user = await session.get(user.__class__, user.id)
        db_user.locale = locale


async def _create_run(user, metadata: dict) -> str:
    async with session_scope() as session:
        run = await RunService(session).create(
            user_id=user.id,
            type_=AgentRunType.DAILY_PLANNING,
            trigger="telegram_command",
        )
        run.metadata_ = metadata
        return str(run.id)


async def test_notifier_sends_bot_api_rich_message_when_enabled(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class FakeBot:
        def __init__(self, token: str) -> None:
            self.session = SimpleNamespace(close=self._close)

        async def _close(self) -> None:
            calls.append(("close", {}))

        async def send_message(self, **kwargs):
            calls.append(("send_message", kwargs))

    async def fake_telegram_api_post(token: str, method: str, payload: dict):
        calls.append((method, payload | {"token": token}))
        return {"ok": True, "result": {"message_id": 10}}

    monkeypatch.setattr("aiogram.Bot", FakeBot)
    monkeypatch.setattr(notifier, "_telegram_api_post", fake_telegram_api_post)
    monkeypatch.setattr(
        notifier,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_bot_token="123:test",
            telegram_use_rich_messages=True,
            mini_app_url="https://app.example/app/",
        ),
    )

    delivered = await notifier.send_telegram_message(
        SimpleNamespace(telegram_chat_id=777, telegram_user_id=777),
        "📅 Сегодня\n🟦 13:00 Standup · 15м",
        rich_html="<p><b>📅 Сегодня</b></p><p><b>🟦 13:00</b> Standup · 15м</p>",
        open_app_button=True,
        open_app_button_label="✨ Открыть Lumi",
    )

    assert delivered is True
    assert [name for name, _ in calls] == ["sendRichMessage", "close"]
    payload = calls[0][1]
    assert payload["token"] == "123:test"
    assert payload["rich_message"]["html"].startswith("<p><b>📅 Сегодня</b></p>")
    assert payload["rich_message"]["skip_entity_detection"] is True
    assert payload["reply_markup"]["inline_keyboard"][0][0]["text"] == "✨ Открыть Lumi"
    assert "web_app" in payload["reply_markup"]["inline_keyboard"][0][0]


async def test_notifier_falls_back_to_plain_message_when_rich_send_fails(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class FakeBot:
        def __init__(self, token: str) -> None:
            self.session = SimpleNamespace(close=self._close)

        async def _close(self) -> None:
            calls.append(("close", {}))

        async def send_message(self, **kwargs):
            calls.append(("send_message", kwargs))

    async def fake_telegram_api_post(token: str, method: str, payload: dict):
        calls.append((method, payload | {"token": token}))
        raise RuntimeError("rich unsupported")

    monkeypatch.setattr("aiogram.Bot", FakeBot)
    monkeypatch.setattr(notifier, "_telegram_api_post", fake_telegram_api_post)
    monkeypatch.setattr(
        notifier,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_bot_token="123:test",
            telegram_use_rich_messages=True,
            mini_app_url="https://app.example/app/",
        ),
    )

    delivered = await notifier.send_telegram_message(
        SimpleNamespace(telegram_chat_id=777, telegram_user_id=777),
        "📅 Сегодня\n🟦 13:00 Standup · 15м",
        rich_html="<p><b>📅 Сегодня</b></p><p><b>🟦 13:00</b> Standup · 15м</p>",
        open_app_button=True,
    )

    assert delivered is True
    assert [name for name, _ in calls] == ["sendRichMessage", "send_message", "close"]
    fallback = calls[1][1]
    assert fallback["text"] == "📅 Сегодня\n🟦 13:00 Standup · 15м"
    assert "parse_mode" not in fallback
    assert fallback["reply_markup"].inline_keyboard[0][0].text == "✨ Открыть Lumi"


async def test_run_daily_planning_sends_rich_schedule_for_proposed_blocks(monkeypatch, user):
    sent: list[dict] = []
    await _set_locale(user, "en")
    run_id = await _create_run(user, {"reply_language": "ru"})
    start = local_to_utc(datetime(2026, 6, 24, 15, 0), user.timezone)
    event = SimpleNamespace(
        id=uuid.uuid4(),
        title="Deep work",
        start_at=start,
        end_at=start + timedelta(hours=1),
    )

    async def fake_propose_day_plan(self, user_arg, *, day=None, agent_run_id=None):
        return "Plan ready.\n\nProposed blocks (waiting for confirmation):\n• 15:00–16:00 Deep work", [event]

    async def fake_send_telegram_message(user_arg, text, **kwargs):
        sent.append({"text": text, **kwargs})
        return True

    monkeypatch.setattr("lumi.services.planning.PlanningService.propose_day_plan", fake_propose_day_plan)
    monkeypatch.setattr("lumi.services.notifier.send_telegram_message", fake_send_telegram_message)

    result = await jobs.run_daily_planning({}, str(user.id), agent_run_id=run_id, notify=True)

    assert result == "plan: 1 blocks proposed"
    assert sent
    assert sent[0]["text"].startswith("📅 План дня, Ср, 24.06")
    assert sent[0]["rich_html"].startswith("<h4>📅 План дня, Ср, 24.06</h4>")
    assert "15:00  Deep work · 1ч" in sent[0]["text"]
    assert "1h" not in sent[0]["text"]
    assert "🟪" not in sent[0]["text"]
    assert "🟪" not in sent[0]["rich_html"]
    assert "<th>" not in sent[0]["rich_html"]
    assert sent[0]["open_app_button"] is True
    assert sent[0]["reply_markup"] is None
