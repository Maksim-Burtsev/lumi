from datetime import timedelta

from sqlalchemy import select

from lumi.db.models import Message, MessageRole
from lumi.db.session import session_scope
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.utils.time import utc_now
from lumi.worker.jobs import send_due_reminders

from .conftest import TEST_TELEGRAM_ID


async def test_send_due_reminders_records_task_notification_message(user, monkeypatch):
    sent: list[dict] = []

    async def fake_send_telegram_message(
        user,
        text: str,
        *,
        reply_markup=None,
        capture_message_ids: bool = False,
    ):
        sent.append({
            "text": text,
            "reply_markup": reply_markup,
            "capture_message_ids": capture_message_ids,
        })
        return [9001]

    monkeypatch.setattr(
        "lumi.services.notifier.send_telegram_message",
        fake_send_telegram_message,
    )

    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task = await TaskService(session).create_task(
            u,
            title="Протереть наушники",
            due_at=utc_now() - timedelta(days=1),
            reminder_at=utc_now() - timedelta(minutes=5),
        )
        task_id = task.id

    assert await send_due_reminders({}) == "sent 1"

    async with session_scope() as session:
        messages = (
            await session.execute(
                select(Message).where(Message.role == MessageRole.ASSISTANT)
            )
        ).scalars().all()

    assert sent[0]["capture_message_ids"] is True
    assert len(messages) == 1
    message = messages[0]
    assert message.telegram_message_id == 9001
    assert message.content_json["notification_type"] == "task_reminder"
    assert message.content_json["task_id"] == str(task_id)
    assert message.content_json["task_title"] == "Протереть наушники"
    assert message.content_json["telegram_message_id"] == 9001
    assert message.content_json["due_at"]
    assert message.content_json["reminder_at"]
