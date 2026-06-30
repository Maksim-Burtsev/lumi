#!/usr/bin/env python3
"""Benchmark assistant turns through the backend orchestrator only.

Examples:
  cd backend
  uv run python ../scripts/bench_assistant_turns.py --label branch --order-set main_branch --reps 3
  uv run python ../scripts/bench_assistant_turns.py --compare-main /tmp/main.jsonl --compare-branch /tmp/branch.jsonl

The runner creates fresh Telegram-like users, conversations, media ids, and PNG
bytes for every benchmark row. It calls AssistantOrchestrator.handle_user_message()
directly and writes JSONL plus Markdown reports.
"""

from __future__ import annotations

import argparse
import asyncio
import binascii
import json
import struct
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from time import monotonic, time
from typing import Any

from sqlalchemy import select

from lumi.assistant.media import ImageInput
from lumi.assistant.orchestrator import AssistantOrchestrator
from lumi.db.models import (
    AgentRun,
    CalendarEvent,
    CalendarEventStatus,
    CalendarSource,
    LLMCall,
    Message,
    MessageRole,
    Priority,
    Task,
    TaskStatus,
    ToolCall,
)
from lumi.db.session import session_scope
from lumi.i18n import ensure_language_settings
from lumi.services.users import UserService
from lumi.utils.time import local_now, local_to_utc


@dataclass(frozen=True)
class BenchCase:
    id: str
    text: str
    app_locale: str = "en"
    reply_language_mode: str = "auto"
    reply_language: str = "en"
    media_setup: str = "none"
    image: bool = False
    expects_serial: bool = False
    setup: str | None = None


@dataclass(frozen=True)
class BenchFixture:
    label: str
    run_id: str
    order_set: str
    rep: int
    case_index: int
    case_id: str
    token: str
    serial: str
    png: bytes
    telegram_user_id: int
    telegram_message_id: int
    task_title: str
    task_new_title: str

    @property
    def fixture_id(self) -> str:
        return f"{self.run_id}-{self.label}-{self.order_set}-r{self.rep}-c{self.case_index}-{self.token}"

    @property
    def recent_file_id(self) -> str:
        return f"bench-recent-file-{self.fixture_id}"

    @property
    def recent_file_unique_id(self) -> str:
        return f"bench-recent-unique-{self.fixture_id}"

    @property
    def attached_file_id(self) -> str:
        return f"bench-attached-file-{self.fixture_id}"

    @property
    def attached_file_unique_id(self) -> str:
        return f"bench-attached-unique-{self.fixture_id}"


def next_weekday(now: datetime, weekday: int) -> datetime:
    days = (weekday - now.weekday()) % 7
    if days == 0:
        days = 7
    target = now + timedelta(days=days)
    return datetime(target.year, target.month, target.day, 10, 0)


FONT_5X7 = {
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00001", "00001", "00001", "00001", "10001", "10001", "01110"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
}


def _draw_text(
    pixels: bytearray,
    *,
    width: int,
    x: int,
    y: int,
    text: str,
    scale: int,
    color: tuple[int, int, int],
) -> None:
    cursor = x
    for char in text.upper():
        glyph = FONT_5X7.get(char, FONT_5X7[" "])
        for row_idx, row in enumerate(glyph):
            for col_idx, bit in enumerate(row):
                if bit != "1":
                    continue
                for yy in range(scale):
                    for xx in range(scale):
                        px = cursor + col_idx * scale + xx
                        py = y + row_idx * scale + yy
                        offset = (py * width + px) * 3
                        pixels[offset:offset + 3] = bytes(color)
        cursor += 6 * scale


def _draw_rect(
    pixels: bytearray,
    *,
    width: int,
    x: int,
    y: int,
    rect_width: int,
    rect_height: int,
    thickness: int,
    color: tuple[int, int, int],
) -> None:
    for py in range(y, y + rect_height):
        for px in range(x, x + rect_width):
            border = (
                py < y + thickness
                or py >= y + rect_height - thickness
                or px < x + thickness
                or px >= x + rect_width - thickness
            )
            if border:
                offset = (py * width + px) * 3
                pixels[offset:offset + 3] = bytes(color)


def _png_from_rgb(width: int, height: int, pixels: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
        )

    rows = bytearray()
    stride = width * 3
    for row in range(height):
        rows.append(0)
        rows.extend(pixels[row * stride:(row + 1) * stride])
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b"")


def benchmark_png(serial: str) -> bytes:
    width, height = 860, 150
    pixels = bytearray([255, 255, 255] * width * height)
    _draw_text(pixels, width=width, x=24, y=18, text="LUMI BENCH LABEL", scale=5, color=(30, 30, 30))
    serial_text = f"S/N:{serial}"
    _draw_rect(
        pixels,
        width=width,
        x=18,
        y=78,
        rect_width=820,
        rect_height=50,
        thickness=4,
        color=(220, 20, 20),
    )
    _draw_text(pixels, width=width, x=32, y=88, text=serial_text, scale=4, color=(0, 0, 0))
    return _png_from_rgb(width, height, bytes(pixels))


def serial_media_context(serial: str) -> dict[str, Any]:
    return {
        "summary": "A small device label. The serial number is highlighted in red.",
        "visible_text": [f"S/N:{serial}", "SNID:13502599316"],
        "entities": [
            {
                "type": "other",
                "label": "serial number",
                "value": serial,
                "evidence": "S/N line highlighted in red",
                "confidence": 0.95,
            }
        ],
        "action_relevant_facts": [f"Serial number highlighted in red: {serial}"],
        "instruction_like_text": [],
        "confidence": 0.9,
        "limitations": ["Synthetic benchmark fixture."],
    }


def benchmark_cases() -> list[BenchCase]:
    return [
        BenchCase(id="en_calendar_next_monday", text="what schedule i have for next monday?", app_locale="en"),
        BenchCase(id="ru_calendar_followup_tuesday", text="а на следующий вторник?", app_locale="ru", setup="calendar_followup"),
        BenchCase(id="it_calendar_next_tuesday", text="Che appuntamenti ho martedì prossimo?", app_locale="en"),
        BenchCase(id="ru_generic_small", text="Коротко объясни, зачем нужен фокус на одной задаче.", app_locale="ru"),
        BenchCase(id="ru_task_create", text="Добавь задачу завтра в 10 проверить latency progress {token}", app_locale="ru"),
        BenchCase(
            id="ru_task_update",
            text='Переименуй задачу "{task_title}" в "{task_new_title}"',
            app_locale="ru",
            setup="task_update",
        ),
        BenchCase(id="recent_media_unrelated_calendar", text="what schedule i have for next monday?", app_locale="en", media_setup="recent"),
        BenchCase(
            id="recent_media_explicit_en",
            text="send only what is marked in red",
            app_locale="en",
            media_setup="recent",
            expects_serial=True,
        ),
        BenchCase(
            id="recent_media_explicit_ru",
            text="пришли только то, что выделено красным",
            app_locale="ru",
            media_setup="recent",
            expects_serial=True,
        ),
        BenchCase(
            id="recent_media_explicit_it",
            text="mandami solo quello segnato in rosso",
            app_locale="en",
            media_setup="recent",
            expects_serial=True,
        ),
        BenchCase(id="attached_image_question", text="What is in this image?", app_locale="en", image=True),
        BenchCase(
            id="attached_image_exact_ocr",
            text="send only what is marked in red",
            app_locale="en",
            image=True,
            expects_serial=True,
        ),
    ]


def case_by_id() -> dict[str, BenchCase]:
    return {case.id: case for case in benchmark_cases()}


def make_fixture(
    *,
    label: str,
    run_id: str,
    order_set: str,
    rep: int,
    case_index: int,
    case_id: str,
    base_user_id: int,
    message_base: int,
) -> BenchFixture:
    key = f"{run_id}:{label}:{order_set}:{rep}:{case_index}:{case_id}"
    crc = binascii.crc32(key.encode("utf-8")) & 0xFFFFFFFF
    serial = f"LXRJ00C{crc:015d}"[-22:]
    token = f"{crc:08x}"
    return BenchFixture(
        label=label,
        run_id=run_id,
        order_set=order_set,
        rep=rep,
        case_index=case_index,
        case_id=case_id,
        token=token,
        serial=serial,
        png=benchmark_png(serial),
        telegram_user_id=base_user_id + (rep * 1000) + case_index,
        telegram_message_id=message_base + (rep * 1000) + case_index,
        task_title=f"bench latency draft {token}",
        task_new_title=f"bench latency final {token}",
    )


async def seed_calendar(session, user, fixture: BenchFixture) -> dict[str, str]:
    now = local_now(user.timezone)
    monday = next_weekday(now, 0)
    tuesday = next_weekday(now, 1)
    events = [
        (f"{fixture.fixture_id}-next-monday-standup", "Team standup", monday, 30),
        (f"{fixture.fixture_id}-next-monday-review", "Product review", monday.replace(hour=15), 45),
        (f"{fixture.fixture_id}-next-tuesday-dentist", "Dentist", tuesday.replace(hour=11), 60),
        (f"{fixture.fixture_id}-next-tuesday-sync", "Lumi sync", tuesday.replace(hour=16), 30),
    ]
    for external_id, title, start_local, minutes in events:
        session.add(CalendarEvent(
            user_id=user.id,
            source=CalendarSource.INTERNAL,
            external_calendar_id="bench",
            external_event_id=external_id,
            title=title,
            start_at=local_to_utc(start_local, user.timezone),
            end_at=local_to_utc(start_local + timedelta(minutes=minutes), user.timezone),
            timezone=user.timezone,
            all_day=False,
            busy=True,
            status=CalendarEventStatus.CONFIRMED,
            created_by="bench",
            metadata_={"bench": True, "fixture_id": fixture.fixture_id},
        ))
    await session.flush()
    return {"next_monday": monday.date().isoformat(), "next_tuesday": tuesday.date().isoformat()}


async def seed_recent_media(session, user, conversation, fixture: BenchFixture) -> None:
    image_metadata = {
        "file_id": fixture.recent_file_id,
        "file_unique_id": fixture.recent_file_unique_id,
        "mime_type": "image/png",
        "file_size": len(fixture.png),
        "source": "attached",
        "telegram_message_id": fixture.telegram_message_id - 1,
    }
    media_context = serial_media_context(fixture.serial)
    session.add(Message(
        conversation_id=conversation.id,
        user_id=user.id,
        role=MessageRole.USER,
        content=f"[image] benchmark serial sticker {fixture.token}",
        char_count=39 + len(fixture.token),
        metadata_={"images": [image_metadata], "media_context": media_context, "bench": True},
        content_json={"text": "", "images": [image_metadata], "media_context": media_context},
    ))
    await session.flush()


async def seed_calendar_followup(session, user, conversation, fixture: BenchFixture) -> None:
    session.add_all([
        Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.USER,
            content="what schedule i have for next monday?",
            char_count=34,
            metadata_={"bench": True, "fixture_id": fixture.fixture_id},
        ),
        Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.ASSISTANT,
            content="For next Monday you have Team standup and Product review.",
            char_count=58,
            metadata_={"bench": True, "fixture_id": fixture.fixture_id},
        ),
    ])
    await session.flush()


async def seed_task_for_update(session, user, fixture: BenchFixture) -> None:
    session.add(Task(
        user_id=user.id,
        title=fixture.task_title,
        status=TaskStatus.ACTIVE,
        priority=Priority.MEDIUM,
        project=None,
        tags=[],
        source="bench",
        created_by="bench",
    ))
    await session.flush()


def render_case_text(case: BenchCase, fixture: BenchFixture) -> str:
    return case.text.format(
        token=fixture.token,
        serial=fixture.serial,
        task_title=fixture.task_title,
        task_new_title=fixture.task_new_title,
    )


def short_reply(text: str, limit: int = 180) -> str:
    compact = " ".join((text or "").split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def tool_names(tool_calls: list[ToolCall] | list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for call in tool_calls:
        name = call.get("tool_name") if isinstance(call, dict) else call.tool_name
        if name:
            names.append(str(name))
    return names


def has_cyrillic(text: str) -> bool:
    return any("а" <= char.lower() <= "я" or char.lower() == "ё" for char in text)


def calendar_reply_quality(case_id: str, reply_text: str) -> str | None:
    if case_id in {"en_calendar_next_monday", "recent_media_unrelated_calendar"}:
        if "Team standup" not in reply_text or "Product review" not in reply_text:
            return "fail: missing Monday calendar events"
    elif case_id in {"ru_calendar_followup_tuesday", "it_calendar_next_tuesday"}:
        if "Dentist" not in reply_text or "Lumi sync" not in reply_text:
            return "fail: missing Tuesday calendar events"
    else:
        return None
    if case_id == "it_calendar_next_tuesday" and has_cyrillic(reply_text):
        return "fail: Italian request rendered in Russian"
    return "pass"


def quality_verdict(
    case: BenchCase,
    *,
    llm_kinds: list[str],
    tool_kinds: list[str],
    reply_text: str,
    expected_serial: str,
) -> str:
    if case.expects_serial:
        return "pass" if expected_serial.upper() in reply_text.upper() else f"fail: missing serial {expected_serial}"
    if case.id == "recent_media_unrelated_calendar":
        if "media_reference" in llm_kinds or "focused_vision" in llm_kinds:
            return "fail: media path called"
        calendar_quality = calendar_reply_quality(case.id, reply_text)
        return calendar_quality or ("pass" if "read_calendar_events" in tool_kinds else "check: no calendar tool")
    if case.image:
        return "pass" if "media_understanding" in llm_kinds else "fail: no media_understanding"
    if "calendar" in case.id:
        calendar_quality = calendar_reply_quality(case.id, reply_text)
        return calendar_quality or ("pass" if "read_calendar_events" in tool_kinds else "check: no calendar tool")
    if case.id == "ru_task_create":
        return "pass" if "create_task" in tool_kinds else "check: no create_task"
    if case.id == "ru_task_update":
        return "pass" if "rename_task" in tool_kinds or "update_task" in tool_kinds else "check: no update tool"
    return "pass" if reply_text else "check"


async def run_case(case: BenchCase, *, fixture: BenchFixture) -> dict[str, Any]:
    progress_events: list[dict[str, Any]] = []
    started = monotonic()

    async def on_progress(status_text: str) -> None:
        progress_events.append({"elapsed_ms": int((monotonic() - started) * 1000), "status": str(status_text)})

    async def image_loader(metadata: dict[str, Any]) -> ImageInput:
        return ImageInput(
            data=fixture.png,
            mime_type=metadata.get("mime_type") or "image/png",
            file_id=metadata.get("file_id") or fixture.recent_file_id,
            file_unique_id=metadata.get("file_unique_id") or fixture.recent_file_unique_id,
            file_size=len(fixture.png),
            source="recent",
            telegram_message_id=metadata.get("telegram_message_id"),
        )

    image = None
    if case.image:
        image = ImageInput(
            data=fixture.png,
            mime_type="image/png",
            file_id=fixture.attached_file_id,
            file_unique_id=fixture.attached_file_unique_id,
            file_size=len(fixture.png),
            source="attached",
            telegram_message_id=fixture.telegram_message_id,
        )

    text = render_case_text(case, fixture)
    dates: dict[str, str] = {}
    try:
        async with session_scope() as session:
            users = UserService(session)
            user = await users.ensure_user(
                fixture.telegram_user_id,
                telegram_chat_id=fixture.telegram_user_id,
                language_code=case.app_locale,
            )
            user.locale = case.app_locale
            settings = ensure_language_settings(user.settings)
            settings["reply_language_mode"] = case.reply_language_mode
            settings["reply_language"] = case.reply_language
            user.settings = settings
            conversation = await users.ensure_main_conversation(user)
            dates = await seed_calendar(session, user, fixture)
            if case.media_setup == "recent":
                await seed_recent_media(session, user, conversation, fixture)
            if case.setup == "calendar_followup":
                await seed_calendar_followup(session, user, conversation, fixture)
            if case.setup == "task_update":
                await seed_task_for_update(session, user, fixture)

            orchestrator = AssistantOrchestrator(session)
            result = await orchestrator.handle_user_message(
                telegram_user_id=fixture.telegram_user_id,
                telegram_chat_id=fixture.telegram_user_id,
                telegram_message_id=fixture.telegram_message_id,
                text=text,
                image=image,
                image_loader=image_loader,
                on_progress=on_progress,
                touch_last_seen=False,
            )
            total_ms = int((monotonic() - started) * 1000)
            llm_calls = (
                await session.execute(
                    select(LLMCall).where(LLMCall.agent_run_id == result.agent_run_id).order_by(LLMCall.created_at)
                )
            ).scalars().all()
            calls = (
                await session.execute(
                    select(ToolCall).where(ToolCall.agent_run_id == result.agent_run_id).order_by(ToolCall.created_at)
                )
            ).scalars().all()
            run = await session.get(AgentRun, result.agent_run_id)
    except Exception as exc:  # noqa: BLE001 - benchmark rows should capture failures and continue.
        total_ms = int((monotonic() - started) * 1000)
        error_text = f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else exc!r}"
        return {
            "label": fixture.label,
            "run_id": fixture.run_id,
            "order_set": fixture.order_set,
            "rep": fixture.rep,
            "case_index": fixture.case_index,
            "case_id": case.id,
            "fixture_id": fixture.fixture_id,
            "language_mode": case.reply_language_mode,
            "app_locale": case.app_locale,
            "input": text,
            "media_setup": "attached_image" if case.image else case.media_setup,
            "expected_serial": fixture.serial if case.expects_serial or case.media_setup == "recent" or case.image else None,
            "dates": dates,
            "progress_events": progress_events,
            "llm_calls": [],
            "tool_calls": [],
            "latency_ms": {},
            "total_ms": total_ms,
            "first_progress_ms": progress_events[0]["elapsed_ms"] if progress_events else None,
            "reply_text": "",
            "reply_short": "",
            "quality_verdict": f"fail: exception {error_text}",
            "error": error_text,
        }

    llm_kinds = [call.request_kind for call in llm_calls]
    tool_kinds = tool_names(calls)
    return {
        "label": fixture.label,
        "run_id": fixture.run_id,
        "order_set": fixture.order_set,
        "rep": fixture.rep,
        "case_index": fixture.case_index,
        "case_id": case.id,
        "fixture_id": fixture.fixture_id,
        "language_mode": case.reply_language_mode,
        "app_locale": case.app_locale,
        "input": text,
        "media_setup": "attached_image" if case.image else case.media_setup,
        "expected_serial": fixture.serial if case.expects_serial or case.media_setup == "recent" or case.image else None,
        "dates": dates,
        "progress_events": progress_events,
        "llm_calls": [
            {
                "request_kind": call.request_kind,
                "status": call.status,
                "latency_ms": call.latency_ms,
                "provider": call.provider,
                "model": call.model,
            }
            for call in llm_calls
        ],
        "tool_calls": [
            {
                "tool_name": call.tool_name,
                "status": call.status,
                "requires_confirmation": call.requires_confirmation,
            }
            for call in calls
        ],
        "latency_ms": (run.metadata_ or {}).get("latency_ms") if run is not None else {},
        "total_ms": total_ms,
        "first_progress_ms": progress_events[0]["elapsed_ms"] if progress_events else None,
        "reply_text": result.reply_text,
        "reply_short": short_reply(result.reply_text),
        "quality_verdict": quality_verdict(
            case,
            llm_kinds=llm_kinds,
            tool_kinds=tool_kinds,
            reply_text=result.reply_text,
            expected_serial=fixture.serial,
        ),
    }


def seconds(ms: int | None) -> str:
    return "-" if ms is None else f"{ms / 1000:.1f}s"


def markdown_table(label: str, rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# Assistant Turn Benchmark: {label}",
        "",
        "| order | rep | case | locale/mode | media | total | first progress | llm calls | tools | quality | reply |",
        "|---|---:|---|---:|---|---:|---:|---|---|---|---|",
    ]
    for row in rows:
        llm = ", ".join(call["request_kind"] for call in row["llm_calls"]) or "-"
        tools = ", ".join(call["tool_name"] for call in row["tool_calls"]) or "-"
        locale = f"{row['app_locale']}/{row['language_mode']}"
        reply = row["reply_short"].replace("|", "\\|")
        lines.append(
            f"| `{row['order_set']}` | {row['rep']} | `{row['case_id']}` | {locale} | {row['media_setup']} | "
            f"{seconds(row['total_ms'])} | {seconds(row['first_progress_ms'])} | {llm} | {tools} | "
            f"{row['quality_verdict']} | {reply} |"
        )
    return "\n".join(lines) + "\n"


def read_rows(paths: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        with Path(path).expanduser().open(encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                payload = json.loads(line)
                if line_number == 1 and "case_id" not in payload:
                    continue
                rows.append(payload)
    return rows


def calls_summary(row: dict[str, Any]) -> str:
    return ", ".join(call["request_kind"] for call in row.get("llm_calls") or []) or "-"


def reply_for_compare(row: dict[str, Any]) -> str:
    return short_reply(str(row.get("reply_text") or "")).replace("|", "\\|")


def row_quality(row: dict[str, Any]) -> str:
    case = case_by_id().get(str(row.get("case_id")))
    if case is None:
        return str(row.get("quality_verdict") or "check")
    return quality_verdict(
        case,
        llm_kinds=[str(call.get("request_kind")) for call in row.get("llm_calls") or []],
        tool_kinds=[str(call.get("tool_name")) for call in row.get("tool_calls") or []],
        reply_text=str(row.get("reply_text") or ""),
        expected_serial=str(row.get("expected_serial") or ""),
    )


def combined_quality(main_row: dict[str, Any], branch_row: dict[str, Any]) -> str:
    main_quality = row_quality(main_row)
    branch_quality = row_quality(branch_row)
    if main_quality.startswith("pass") and branch_quality.startswith("pass"):
        return "pass"
    return f"main={main_quality}; branch={branch_quality}"


def format_delta(branch_ms: int, main_ms: int) -> str:
    delta = (branch_ms - main_ms) / 1000
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f}s"


def comparison_markdown(main_rows: list[dict[str, Any]], branch_rows: list[dict[str, Any]]) -> str:
    cases = case_by_id()
    case_order = {case.id: idx for idx, case in enumerate(benchmark_cases(), start=1)}
    main_by_key = {(row["order_set"], row["rep"], row["case_id"]): row for row in main_rows}
    branch_by_key = {(row["order_set"], row["rep"], row["case_id"]): row for row in branch_rows}
    keys = sorted(
        set(main_by_key) & set(branch_by_key),
        key=lambda key: (key[0], int(key[1]), case_order.get(key[2], 999), key[2]),
    )

    lines = [
        "# Assistant Turn Benchmark Comparison",
        "",
        "| case | rep | order | main total | branch total | delta | main calls | branch calls | main reply | branch reply | quality |",
        "|---|---:|---|---:|---:|---:|---|---|---|---|---|",
    ]
    for key in keys:
        main_row = main_by_key[key]
        branch_row = branch_by_key[key]
        lines.append(
            f"| `{key[2]}` | {key[1]} | `{key[0]}` | {seconds(main_row['total_ms'])} | "
            f"{seconds(branch_row['total_ms'])} | {format_delta(branch_row['total_ms'], main_row['total_ms'])} | "
            f"{calls_summary(main_row)} | {calls_summary(branch_row)} | {reply_for_compare(main_row)} | "
            f"{reply_for_compare(branch_row)} | {combined_quality(main_row, branch_row)} |"
        )

    lines.extend(["", "## Median Summary", ""])
    lines.append("| case | main median | branch median | delta | main calls | branch calls | quality |")
    lines.append("|---|---:|---:|---:|---|---|---|")
    for case_id in sorted(cases, key=lambda item: case_order.get(item, 999)):
        paired = [(main_by_key[key], branch_by_key[key]) for key in keys if key[2] == case_id]
        if not paired:
            continue
        main_med = int(median(row[0]["total_ms"] for row in paired))
        branch_med = int(median(row[1]["total_ms"] for row in paired))
        main_calls = "; ".join(sorted({calls_summary(row[0]) for row in paired}))
        branch_calls = "; ".join(sorted({calls_summary(row[1]) for row in paired}))
        quality = "pass" if all(combined_quality(*row) == "pass" for row in paired) else "check/fail"
        lines.append(
            f"| `{case_id}` | {seconds(main_med)} | {seconds(branch_med)} | "
            f"{format_delta(branch_med, main_med)} | {main_calls} | {branch_calls} | {quality} |"
        )
    return "\n".join(lines) + "\n"


def prepare_output_dir(base_dir: str, run_id: str) -> Path:
    out_dir = Path(base_dir).expanduser().resolve() / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


async def run_benchmark(args: argparse.Namespace) -> None:
    run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = prepare_output_dir(args.out_dir, run_id)
    base_user_id = args.base_user_id or (880000000 + int(time()) % 1000000)
    message_base = args.message_base or (int(time()) % 1000000)
    selected_cases = benchmark_cases()
    if args.case:
        wanted = set(args.case)
        selected_cases = [case for case in selected_cases if case.id in wanted]
        missing = wanted - {case.id for case in selected_cases}
        if missing:
            raise SystemExit(f"Unknown benchmark case(s): {', '.join(sorted(missing))}")

    rows: list[dict[str, Any]] = []
    for rep in range(1, args.reps + 1):
        for case_index, case in enumerate(selected_cases, start=1):
            fixture = make_fixture(
                label=args.label,
                run_id=run_id,
                order_set=args.order_set,
                rep=rep,
                case_index=case_index,
                case_id=case.id,
                base_user_id=base_user_id,
                message_base=message_base,
            )
            row = await run_case(case, fixture=fixture)
            rows.append(row)
            print(json.dumps({
                "label": row["label"],
                "order_set": row["order_set"],
                "rep": row["rep"],
                "case_id": row["case_id"],
                "total": seconds(row["total_ms"]),
                "llm_calls": [call["request_kind"] for call in row["llm_calls"]],
                "tool_calls": [call["tool_name"] for call in row["tool_calls"]],
                "quality_verdict": row["quality_verdict"],
            }, ensure_ascii=False), flush=True)

    jsonl_path = out_dir / f"{args.label}-{args.order_set}.jsonl"
    md_path = out_dir / f"{args.label}-{args.order_set}.md"
    meta = {
        "label": args.label,
        "run_id": run_id,
        "order_set": args.order_set,
        "reps": args.reps,
        "base_user_id": base_user_id,
        "message_base": message_base,
        "case_count": len(selected_cases),
    }
    with jsonl_path.open("w", encoding="utf-8") as file:
        file.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    md_path.write_text(markdown_table(f"{args.label} {args.order_set}", rows), encoding="utf-8")
    print(f"\nWrote {jsonl_path}", flush=True)
    print(f"Wrote {md_path}", flush=True)


def run_compare(args: argparse.Namespace) -> None:
    main_rows = read_rows(args.compare_main)
    branch_rows = read_rows(args.compare_branch)
    output = comparison_markdown(main_rows, branch_rows)
    if args.compare_out:
        path = Path(args.compare_out).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
        print(f"Wrote {path}")
    else:
        print(output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="branch", choices=["main", "branch"], help="Label used in output filenames.")
    parser.add_argument("--order-set", default="main_branch", choices=["main_branch", "branch_main"])
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--case", action="append", help="Run only one benchmark case id. Can be passed multiple times.")
    parser.add_argument("--out-dir", default="../output/assistant_turns", help="Output directory.")
    parser.add_argument("--run-id", default=None, help="Shared run id for related main/branch runs.")
    parser.add_argument("--base-user-id", type=int, default=None, help="Base Telegram user id.")
    parser.add_argument("--message-base", type=int, default=None, help="Base Telegram message id.")
    parser.add_argument("--compare-main", nargs="+", help="Main JSONL files to compare.")
    parser.add_argument("--compare-branch", nargs="+", help="Branch JSONL files to compare.")
    parser.add_argument("--compare-out", help="Markdown output path for comparison.")
    args = parser.parse_args()
    if bool(args.compare_main) != bool(args.compare_branch):
        raise SystemExit("--compare-main and --compare-branch must be provided together")
    if args.reps < 1:
        raise SystemExit("--reps must be >= 1")
    return args


def main() -> None:
    args = parse_args()
    if args.compare_main and args.compare_branch:
        run_compare(args)
        return
    asyncio.run(run_benchmark(args))


if __name__ == "__main__":
    main()
