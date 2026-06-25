from __future__ import annotations

from datetime import datetime, timedelta

from lumi.bot.schedule_messages import ScheduleMessageItem, render_schedule_message
from lumi.utils.time import local_to_utc


def test_render_schedule_message_groups_week_and_escapes_rich_links():
    tz = "Europe/Moscow"
    start = local_to_utc(datetime(2026, 6, 24, 13, 0), tz)
    items = [
        ScheduleMessageItem(
            title='Тутория <2.0> "стендап"',
            start_at=start,
            end_at=start + timedelta(minutes=15),
            kind="event",
            meeting_url="https://meet.example/a?x=1&y=2",
        ),
        ScheduleMessageItem(
            title="Календарь стендап",
            start_at=start + timedelta(minutes=15),
            end_at=start + timedelta(minutes=30),
            kind="event",
        ),
        ScheduleMessageItem(
            title="Ретро календарь",
            start_at=start + timedelta(hours=2),
            end_at=start + timedelta(hours=3),
            kind="event",
        ),
        ScheduleMessageItem(
            title="Груминг",
            start_at=start + timedelta(days=1),
            end_at=start + timedelta(days=1, hours=1),
            kind="event",
        ),
    ]

    rendered = render_schedule_message(
        title="📅 24.06 - 25.06",
        items=items,
        timezone=tz,
        language="ru",
        window_start=start,
        window_end=start + timedelta(days=2),
        include_free_gaps=True,
        max_items=10,
    )

    assert rendered.plain_text.startswith("📅 24.06 - 25.06")
    assert rendered.rich_html.startswith("<h4>📅 24.06 - 25.06</h4>")
    assert "<table bordered striped><caption><b>24.06</b></caption>" in rendered.rich_html
    assert "<th>" not in rendered.rich_html
    assert not any(icon in rendered.rich_html for icon in ("🟦", "🟩", "🟪", "⬜"))
    assert "13:00  Тутория <2.0> \"стендап\" · 15м  ↗" in rendered.plain_text
    assert "https://meet.example" not in rendered.plain_text
    assert (
        '<tr><td><b>13:00</b></td>'
        '<td>Тутория &lt;2.0&gt; &quot;стендап&quot; · 15м '
        '<a href="https://meet.example/a?x=1&amp;y=2">↗</a></td></tr>'
    ) in rendered.rich_html
    assert "\n13:30  Свободно · 1ч 30м" in rendered.plain_text
    assert (
        '<tr><td><b>13:30</b></td><td><i>Свободно · 1ч 30м</i></td></tr>'
    ) in rendered.rich_html
    assert "<table bordered striped><caption><b>25.06</b></caption>" in rendered.rich_html
    assert "\n" not in rendered.rich_html


def test_render_schedule_message_limits_rows_and_reports_hidden_count():
    tz = "Europe/Moscow"
    start = local_to_utc(datetime(2026, 6, 24, 9, 0), tz)
    items = [
        ScheduleMessageItem(
            title=f"Event {index}",
            start_at=start + timedelta(hours=index),
            end_at=start + timedelta(hours=index, minutes=30),
            kind="event",
        )
        for index in range(7)
    ]

    rendered = render_schedule_message(
        title="📅 Сегодня, 24.06",
        items=items,
        timezone=tz,
        language="ru",
        max_items=5,
    )

    assert "Event 0" in rendered.plain_text
    assert "Event 4" in rendered.plain_text
    assert "Event 5" not in rendered.plain_text
    assert "\n+ ещё 2 в календаре" in rendered.plain_text
    assert "<footer><i>+ ещё 2 в календаре</i></footer>" in rendered.rich_html


def test_render_schedule_message_marks_proposed_blocks_without_color_noise():
    tz = "Europe/Moscow"
    start = local_to_utc(datetime(2026, 6, 24, 15, 0), tz)
    rendered = render_schedule_message(
        title="📅 План дня",
        items=[
            ScheduleMessageItem(
                title="Deep work",
                start_at=start,
                end_at=start + timedelta(hours=1),
                kind="proposed",
                action_id="abc",
            )
        ],
        timezone=tz,
        language="ru",
    )

    assert "15:00  Deep work · 1ч" in rendered.plain_text
    assert "🟪" not in rendered.plain_text
    assert "🟪" not in rendered.rich_html
    assert rendered.buttons == []


def test_render_schedule_message_uses_week_limit_for_multi_day_window():
    tz = "Europe/Moscow"
    start = local_to_utc(datetime(2026, 6, 22, 9, 0), tz)
    items = [
        ScheduleMessageItem(
            title=f"Event {index}",
            start_at=start + timedelta(hours=index * 3),
            end_at=start + timedelta(hours=index * 3, minutes=30),
            kind="event",
        )
        for index in range(12)
    ]

    rendered = render_schedule_message(
        title="📅 22.06 - 28.06",
        items=items,
        timezone=tz,
        language="ru",
        window_start=start,
        window_end=start + timedelta(days=7),
    )

    assert "Event 11" in rendered.plain_text
    assert "+ ещё" not in rendered.plain_text
    assert "<table bordered striped><caption><b>22.06</b></caption>" in rendered.rich_html
    assert "<table bordered striped><caption><b>23.06</b></caption>" in rendered.rich_html
