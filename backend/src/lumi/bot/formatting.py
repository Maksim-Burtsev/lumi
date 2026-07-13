"""Plain-text formatting for Telegram replies (no markdown — no escaping bugs)."""

from __future__ import annotations

import re

from lumi.db.models import Task
from lumi.utils.text import ru_plural
from lumi.utils.time import fmt_local


def telegram_plain_text(text: str) -> str:
    """Best-effort cleanup when an LLM leaks Markdown into Telegram plain text."""
    text = re.sub(r"```[a-zA-Z0-9_-]*\n?(.*?)```", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?m)^\s*[-*]\s+", "• ", text)
    return text.strip()


def rich_html_requires_rich_message(html: str) -> bool:
    """Return True for tags supported by Rich Messages but unsafe for sendMessage HTML."""
    return bool(re.search(
        r"</?(?:p|h[1-6]|ul|ol|li|details|summary|table|caption|tr|td|th|footer|hr)\b",
        html,
        re.I,
    ))


def format_today(payload: dict, tz: str) -> str:
    summary = payload["summary"]
    lines = [payload["greeting"] + "!"]

    bits = []
    if summary["meetings_today"]:
        n = summary["meetings_today"]
        bits.append(f"{n} {ru_plural(n, 'встреча', 'встречи', 'встреч')}")
    if summary["tasks_active"]:
        n = summary["tasks_active"]
        bits.append(f"{n} {ru_plural(n, 'задача', 'задачи', 'задач')}")
    lines.append("Сегодня: " + (" · ".join(bits) if bits else "спокойный день, ничего срочного"))

    if payload["timeline"]:
        lines.append("")
        lines.append("Расписание:")
        for item in payload["timeline"][:8]:
            from datetime import datetime

            start = datetime.fromisoformat(item["start_at"])
            mark = " (предложено)" if item["kind"] == "proposed" else ""
            lines.append(f"  {fmt_local(start, tz, '%H:%M')}  {item['title']}{mark}")

    if payload["needs_attention"]:
        lines.append("")
        lines.append("Требует внимания:")
        for item in payload["needs_attention"][:5]:
            suffix = f" — {item['subtitle']}" if item.get("subtitle") else ""
            lines.append(f"  • {item['title']}{suffix}")

    if summary["tasks_overdue"]:
        n = summary["tasks_overdue"]
        lines.append("")
        lines.append(f"⚠ Просрочено: {n} {ru_plural(n, 'задача', 'задачи', 'задач')}")

    return "\n".join(lines)


def format_tasks(tasks: list[Task], tz: str) -> str:
    if not tasks:
        return ("Активных задач нет.\n\n"
                "Напиши мне, например: «Напомни завтра в 10 позвонить Ивану» — и задача появится.")
    priority_marks = {"urgent": "‼️", "high": "❗", "medium": "•", "low": "·"}
    lines = ["Твои задачи:"]
    for task in tasks[:20]:
        mark = priority_marks.get(task.priority.value, "•")
        line = f"{mark} {task.title}"
        details = []
        if task.due_at:
            details.append(f"срок {fmt_local(task.due_at, tz)}")
        if task.reminder_at:
            details.append(f"напомню {fmt_local(task.reminder_at, tz)}")
        if task.project:
            details.append(task.project)
        if details:
            line += f"\n   {' · '.join(details)}"
        lines.append(line)
    if len(tasks) > 20:
        lines.append(f"… и еще {len(tasks) - 20} в Mini App")
    return "\n".join(lines)


HELP_TEXT = """Я Lumi — твой помощник по личной продуктивности.

Просто пиши мне обычным языком:
• «Напомни завтра в 10 написать Саше»
• «Сделай план на сегодня с учетом встреч»
• «Что у меня сегодня в календаре?»
• «Запомни: утренние встречи лучше после 10:00»

Команды:
/intro — знакомство: 5 вопросов, чтобы я понимал твой контекст
/today — что сегодня
/tasks — активные задачи
/plan — собрать план дня
/app — открыть Mini App
/settings — настройки и статус

Изображения и другие вложения не анализирую. Изменения во внешнем календаре делаю только после твоего подтверждения."""
