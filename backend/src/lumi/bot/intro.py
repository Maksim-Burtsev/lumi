"""Onboarding interview: /intro — Lumi asks, answers become memory.

State lives in user.settings["intro_step"]; answers are stored as high-importance
memories so they enter every future context. "-" skips a question, /cancel aborts.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.memory_service import MemoryService
from lumi.assistant.schemas import MemoryCandidate
from lumi.db.models import User

MemoryCandidateKind = Literal["preference", "fact", "project", "instruction", "contact", "workflow", "other"]

# (memory kind, question, prefix for the stored memory text)
INTRO_QUESTIONS: list[tuple[MemoryCandidateKind, str, str]] = [
    ("fact",
     "Чем ты занимаешься? Роль, компания или проект — пару фраз.",
     "Род занятий"),
    ("project",
     "Какие 1–3 проекта или цели сейчас для тебя главные?",
     "Главные проекты"),
    ("preference",
     "Какой у тебя обычный рабочий ритм? Например: «работаю 10–19, встречи утром, глубокая работа после обеда».",
     "Рабочий ритм"),
    ("preference",
     "С какими задачами и планированием тебе чаще всего нужна помощь?",
     "Приоритетная помощь"),
    ("instruction",
     "Как мне лучше отвечать? Например: «коротко и по делу», «с деталями», «предлагай следующие шаги».",
     "Стиль ответов"),
]

INTRO_START_TEXT = (
    "Давай познакомимся — задам 5 коротких вопросов, чтобы понимать твой контекст.\n"
    "Ответ «-» пропускает вопрос, /cancel — прервать.\n\n"
    f"1/5. {INTRO_QUESTIONS[0][1]}"
)

INTRO_DONE_TEXT = (
    "Спасибо, записал! Теперь я учитываю это в каждом ответе.\n\n"
    "Память используется как внутренний рабочий контекст Lumi.\n"
    "Дальше просто пиши мне про задачи, календарь, фокус и планы."
)


def intro_step(user: User) -> int | None:
    step = (user.settings or {}).get("intro_step")
    return int(step) if step is not None else None


def set_intro_step(user: User, step: int | None) -> None:
    settings = dict(user.settings or {})
    if step is None:
        settings.pop("intro_step", None)
    else:
        settings["intro_step"] = step
    user.settings = settings


async def handle_intro_answer(
    session: AsyncSession, user: User, text: str
) -> tuple[str, bool]:
    """Process one interview answer. Returns (reply, finished)."""
    step = intro_step(user)
    if step is None or not 0 <= step < len(INTRO_QUESTIONS):
        set_intro_step(user, None)
        return "Интервью уже завершено.", True

    answer = text.strip()
    if answer.lower() in ("/cancel", "отмена"):
        set_intro_step(user, None)
        return "Ок, прервал. Вернуться можно командой /intro.", True

    if answer and answer != "-":
        kind, _, prefix = INTRO_QUESTIONS[step]
        await MemoryService(session).store_candidate(
            user,
            MemoryCandidate(
                kind=kind, text=f"{prefix}: {answer}", importance=5,
                confidence=0.99, requires_confirmation=False,
            ),
            actor="user",
        )

    next_step = step + 1
    if next_step >= len(INTRO_QUESTIONS):
        set_intro_step(user, None)
        return INTRO_DONE_TEXT, True
    set_intro_step(user, next_step)
    return f"{next_step + 1}/5. {INTRO_QUESTIONS[next_step][1]}", False
