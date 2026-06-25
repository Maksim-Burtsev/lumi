"""Compact Telegram schedule cards with rich-message HTML fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import escape
from typing import Any

from lumi.utils.text import truncate
from lumi.utils.time import utc_to_local

FREE_GAP_MINUTES = 15
DEFAULT_MAX_ITEMS = 8
WEEK_MAX_ITEMS = 24
MAX_TITLE_CHARS = 64


@dataclass(frozen=True)
class ScheduleMessageButton:
    text: str
    callback_data: str


@dataclass(frozen=True)
class ScheduleMessageItem:
    title: str
    start_at: datetime
    end_at: datetime
    kind: str = "event"
    meeting_url: str | None = None
    action_id: str | None = None
    busy: bool = True


@dataclass(frozen=True)
class RenderedScheduleMessage:
    plain_text: str
    rich_html: str
    buttons: list[list[ScheduleMessageButton]] = field(default_factory=list)
    open_app_button: bool = True
    open_app_button_label: str = "✨ Открыть Lumi"


def render_schedule_message(
    *,
    title: str,
    items: list[ScheduleMessageItem],
    timezone: str,
    language: str | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    include_free_gaps: bool = True,
    max_items: int | None = None,
    confirm_proposed: bool = False,
) -> RenderedScheduleMessage:
    sorted_items = sorted(items, key=lambda item: (item.start_at, item.end_at, item.title))
    visible_limit = max_items if max_items is not None else _default_limit(window_start, window_end, timezone)
    visible_items = sorted_items[:visible_limit]
    hidden_count = max(0, len(sorted_items) - len(visible_items))
    grouped = _spans_multiple_days(visible_items, timezone)

    plain_lines = [title]
    rich_parts = [_rich_heading(title)]
    buttons: list[list[ScheduleMessageButton]] = []
    busy_cursor: datetime | None = None
    current_day: str | None = None
    current_table_caption: str | None = None
    current_table_rows: list[str] = []

    def flush_table() -> None:
        nonlocal current_table_rows
        if current_table_rows:
            rich_parts.append(_rich_table(
                rows=current_table_rows,
                caption=current_table_caption if grouped else None,
                language=language,
            ))
            current_table_rows = []

    for item in visible_items:
        item_day = utc_to_local(item.start_at, timezone).strftime("%d.%m")
        if grouped and item_day != current_day:
            flush_table()
            current_day = item_day
            current_table_caption = item_day
            plain_lines.append("")
            plain_lines.append(item_day)
            busy_cursor = None

        if include_free_gaps and busy_cursor is not None and item.start_at > busy_cursor:
            previous_day = utc_to_local(busy_cursor, timezone).date()
            item_local = utc_to_local(item.start_at, timezone)
            if item_local.date() == previous_day:
                gap = item.start_at - busy_cursor
                if gap >= timedelta(minutes=FREE_GAP_MINUTES):
                    gap_start = utc_to_local(busy_cursor, timezone)
                    free_line = f"{gap_start.strftime('%H:%M')}  {_free_label(language)} · {_duration_text(language, gap)}"
                    plain_lines.append(free_line)
                    current_table_rows.append(_render_free_row(
                        start_at=busy_cursor,
                        duration=gap,
                        timezone=timezone,
                        language=language,
                    ))

        plain_line, rich_row = _render_item(item, timezone, language)
        plain_lines.append(plain_line)
        current_table_rows.append(rich_row)
        if confirm_proposed and item.kind == "proposed" and item.action_id:
            start_label = utc_to_local(item.start_at, timezone).strftime("%H:%M")
            buttons.append([ScheduleMessageButton(
                text=f"✓ Принять {start_label} {truncate(item.title, 24)}",
                callback_data=f"block_confirm:{item.action_id}",
            )])
        if item.busy:
            busy_cursor = max(busy_cursor or item.end_at, item.end_at)

    flush_table()
    if hidden_count:
        more = _more_text(language, hidden_count)
        plain_lines.append(more)
        rich_parts.append(f"<footer><i>{escape(more)}</i></footer>")

    return RenderedScheduleMessage(
        plain_text="\n".join(plain_lines).strip(),
        rich_html="".join(rich_parts).strip(),
        buttons=buttons,
    )


def schedule_items_from_today_timeline(timeline: list[dict[str, Any]]) -> list[ScheduleMessageItem]:
    items: list[ScheduleMessageItem] = []
    for entry in timeline:
        start_raw = entry.get("start_at")
        end_raw = entry.get("end_at")
        title = str(entry.get("title") or "").strip()
        if not start_raw or not end_raw or not title:
            continue
        start_at = datetime.fromisoformat(str(start_raw))
        end_at = datetime.fromisoformat(str(end_raw))
        if end_at <= start_at:
            end_at = start_at + timedelta(minutes=15)
        items.append(ScheduleMessageItem(
            title=title,
            start_at=start_at,
            end_at=end_at,
            kind=str(entry.get("kind") or "event"),
            meeting_url=_metadata_value(entry, "meeting_url"),
            action_id=str(entry["id"]) if entry.get("kind") == "proposed" and entry.get("id") else None,
            busy=bool(entry.get("busy", True)),
        ))
    return items


def render_today_schedule(
    payload: dict[str, Any],
    *,
    timezone: str,
    language: str | None = None,
    max_items: int | None = None,
) -> RenderedScheduleMessage | None:
    items = schedule_items_from_today_timeline(list(payload.get("timeline") or []))
    if not items:
        return None
    return render_schedule_message(
        title=_today_title(payload, language),
        items=items,
        timezone=timezone,
        language=language,
        include_free_gaps=True,
        max_items=max_items,
    )


def schedule_items_from_calendar_events(events: list[Any]) -> list[ScheduleMessageItem]:
    items: list[ScheduleMessageItem] = []
    for event in events:
        kind = "event"
        status = getattr(event, "status", None)
        source = getattr(event, "source", None)
        if getattr(status, "value", status) == "proposed":
            kind = "proposed"
        elif getattr(source, "value", source) == "internal" and getattr(event, "created_by", None) == "agent":
            kind = "focus"
        items.append(ScheduleMessageItem(
            title=event.title,
            start_at=event.start_at,
            end_at=event.end_at,
            kind=kind,
            meeting_url=(getattr(event, "metadata_", {}) or {}).get("meeting_url"),
            action_id=str(event.id) if kind == "proposed" else None,
            busy=bool(getattr(event, "busy", True)),
        ))
    return items


def _render_item(item: ScheduleMessageItem, timezone: str, language: str | None) -> tuple[str, str]:
    start_local = utc_to_local(item.start_at, timezone)
    duration = _duration_text(language, item.end_at - item.start_at)
    title = truncate(item.title, MAX_TITLE_CHARS)
    link_mark = "  ↗" if item.meeting_url else ""
    plain_line = f"{start_local.strftime('%H:%M')}  {title} · {duration}{link_mark}"
    link_html = ""
    if item.meeting_url:
        link_html = f' <a href="{escape(item.meeting_url, quote=True)}">↗</a>'
    rich_row = (
        f"<tr><td><b>{escape(start_local.strftime('%H:%M'))}</b></td>"
        f"<td>{escape(title)} · {escape(duration)}{link_html}</td></tr>"
    )
    return plain_line, rich_row


def _render_free_row(*, start_at: datetime, duration: timedelta, timezone: str, language: str | None) -> str:
    start_local = utc_to_local(start_at, timezone)
    return (
        f"<tr><td><b>{escape(start_local.strftime('%H:%M'))}</b></td>"
        f"<td><i>{escape(_free_label(language))} · {escape(_duration_text(language, duration))}</i></td></tr>"
    )


def _rich_heading(title: str) -> str:
    return f"<h4>{escape(title)}</h4>"


def _rich_table(*, rows: list[str], caption: str | None, language: str | None) -> str:
    caption_html = f"<caption><b>{escape(caption)}</b></caption>" if caption else ""
    return f"<table bordered striped>{caption_html}{''.join(rows)}</table>"


def _duration_text(language: str | None, duration: timedelta) -> str:
    total_minutes = max(1, int(duration.total_seconds() // 60))
    hours, minutes = divmod(total_minutes, 60)
    if _normalized_language(language) == "en":
        parts: list[str] = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        return " ".join(parts) or "0m"
    parts = []
    if hours:
        parts.append(f"{hours}ч")
    if minutes:
        parts.append(f"{minutes}м")
    return " ".join(parts) or "0м"


def _free_label(language: str | None) -> str:
    return "Free" if _normalized_language(language) == "en" else "Свободно"


def _more_text(language: str | None, count: int) -> str:
    return f"+ {count} more in calendar" if _normalized_language(language) == "en" else f"+ ещё {count} в календаре"


def _default_limit(window_start: datetime | None, window_end: datetime | None, timezone: str) -> int:
    if window_start and window_end and utc_to_local(window_start, timezone).date() != utc_to_local(
        window_end - timedelta(seconds=1), timezone
    ).date():
        return WEEK_MAX_ITEMS
    return DEFAULT_MAX_ITEMS


def _spans_multiple_days(items: list[ScheduleMessageItem], timezone: str) -> bool:
    days = {utc_to_local(item.start_at, timezone).date() for item in items}
    return len(days) > 1


def _normalized_language(language: str | None) -> str:
    return (language or "").split("-", 1)[0].lower()


def _metadata_value(entry: dict[str, Any], key: str) -> str | None:
    value = entry.get(key)
    if value is None and isinstance(entry.get("metadata"), dict):
        value = entry["metadata"].get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _today_title(payload: dict[str, Any], language: str | None) -> str:
    date_raw = str(payload.get("date") or "").strip()
    try:
        day = datetime.fromisoformat(date_raw)
        label = day.strftime("%d.%m")
    except ValueError:
        label = date_raw or ""
    if _normalized_language(language) == "en":
        return f"📅 Today, {label}" if label else "📅 Today"
    return f"📅 Сегодня, {label}" if label else "📅 Сегодня"
