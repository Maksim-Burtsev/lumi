"""User-facing replies for task update actions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lumi.db.models import Task


def _is_english(language: str | None) -> bool:
    return (language or "").lower().startswith("en")


def _format_tags(tags: object) -> str:
    if not isinstance(tags, list) or not tags:
        return ""
    return ", ".join(f"#{str(tag).lstrip('#')}" for tag in tags if str(tag).strip())


def format_task_update_reply(
    task: Task,
    updates: Mapping[str, Any],
    *,
    language: str | None = None,
) -> str:
    english = _is_english(language)
    title = task.title

    if set(updates) == {"project"}:
        project = updates.get("project")
        if project:
            if english:
                return f"Moved task “{title}” to project {project}."
            return f"Привязал задачу «{title}» к проекту {project}."
        if english:
            return f"Removed the project from task “{title}”."
        return f"Убрал проект у задачи «{title}»."

    changes: list[str] = []
    if "project" in updates:
        project = updates.get("project")
        changes.append(f"project {project}" if english and project else "removed project" if english else f"проект — {project}" if project else "проект убран")
    if "priority" in updates and updates.get("priority"):
        priority = updates["priority"]
        changes.append(f"priority {priority}" if english else f"приоритет — {priority}")
    if "tags" in updates:
        tags = _format_tags(updates.get("tags"))
        changes.append(f"tags {tags}" if english and tags else "removed tags" if english else f"теги — {tags}" if tags else "теги убраны")
    if "description" in updates:
        changes.append("description updated" if english else "описание обновлено")
    if "title" in updates and updates.get("title"):
        changes.append(f"title “{updates['title']}”" if english else f"название — «{updates['title']}»")

    if not changes:
        return f"Updated task “{title}”." if english else f"Обновил задачу «{title}»."
    if english:
        return f"Updated task “{title}”: {', '.join(changes)}."
    return f"Обновил задачу «{title}»: {', '.join(changes)}."


def format_task_update_no_updates_reply(*, language: str | None = None) -> str:
    if _is_english(language):
        return "I did not understand what to change in the task. Please clarify the change."
    return "Не понял, что изменить в задаче. Уточни изменение."


def format_task_update_not_found_reply(
    *,
    task_query: str | None = None,
    recency_hint: str | None = None,
    language: str | None = None,
) -> str:
    if _is_english(language):
        if task_query:
            return f"I could not find an active task “{task_query}”. Please clarify the title."
        if recency_hint:
            return "I could not find a recent active task. Please clarify the title."
        return "I could not find an active task. Please clarify the title."
    if task_query:
        return f"Не нашёл активную задачу «{task_query}». Уточни название."
    if recency_hint:
        return "Не нашёл недавнюю активную задачу. Уточни название."
    return "Не нашёл активную задачу. Уточни название."


def format_task_update_ambiguous_reply(*, language: str | None = None) -> str:
    if _is_english(language):
        return "Found several matching tasks. Which one should I update?"
    return "Нашёл несколько похожих задач. Какую обновить?"


def format_task_update_choice_prompt(*, language: str | None = None) -> str:
    if _is_english(language):
        return "Choose the task to update."
    return "Выбери задачу для обновления."


def format_task_update_confirmation_prompt(
    title: str,
    *,
    language: str | None = None,
) -> str:
    if _is_english(language):
        return f"Update task “{title}”?"
    return f"Обновить задачу «{title}»?"
