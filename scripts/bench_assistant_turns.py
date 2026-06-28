#!/usr/bin/env python3
"""Benchmark assistant turns through the backend orchestrator only.

Run from repo root:
  cd backend && uv run python ../scripts/bench_assistant_turns.py --label branch

The script uses the configured DATABASE_URL/LLM_PROVIDER/MiniMax env, creates a
dedicated Telegram-like user, calls AssistantOrchestrator.handle_user_message(),
and writes JSONL plus a compact Markdown table.
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
from functools import lru_cache
from pathlib import Path
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
    ToolCall,
)
from lumi.db.session import session_scope
from lumi.i18n import ensure_language_settings
from lumi.services.users import UserService
from lumi.utils.time import local_now, local_to_utc

SERIAL_MEDIA_CONTEXT = {
    "summary": "A small device label. The serial number is highlighted in red.",
    "visible_text": ["S/N:LXRJ00C058135065891601", "SNID:13502599316"],
    "entities": [
        {
            "type": "other",
            "label": "serial number",
            "value": "LXRJ00C058135065891601",
            "evidence": "S/N line highlighted in red",
            "confidence": 0.95,
        }
    ],
    "action_relevant_facts": [
        "Serial number highlighted in red: LXRJ00C058135065891601",
    ],
    "instruction_like_text": [],
    "confidence": 0.9,
    "limitations": ["Synthetic benchmark fixture."],
}


@dataclass(frozen=True)
class BenchCase:
    id: str
    text: str
    app_locale: str = "en"
    reply_language_mode: str = "auto"
    reply_language: str = "en"
    media_setup: str = "none"
    image: bool = False


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


@lru_cache(maxsize=1)
def benchmark_png() -> bytes:
    width, height = 840, 140
    pixels = bytearray([255, 255, 255] * width * height)
    _draw_text(pixels, width=width, x=24, y=20, text="ACER LABEL", scale=5, color=(30, 30, 30))
    serial_text = "S/N:LXRJ00C058135065891601"
    _draw_rect(
        pixels,
        width=width,
        x=18,
        y=76,
        rect_width=794,
        rect_height=46,
        thickness=4,
        color=(220, 20, 20),
    )
    _draw_text(pixels, width=width, x=32, y=84, text=serial_text, scale=4, color=(0, 0, 0))
    return _png_from_rgb(width, height, bytes(pixels))


async def seed_calendar(session, user) -> dict[str, str]:
    now = local_now(user.timezone)
    monday = next_weekday(now, 0)
    tuesday = next_weekday(now, 1)
    events = [
        ("bench-next-monday-standup", "Team standup", monday, 30),
        ("bench-next-monday-review", "Product review", monday.replace(hour=15), 45),
        ("bench-next-tuesday-italian", "Dentist", tuesday.replace(hour=11), 60),
        ("bench-next-tuesday-sync", "Lumi sync", tuesday.replace(hour=16), 30),
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
            metadata_={"bench": True},
        ))
    await session.flush()
    return {
        "next_monday": monday.date().isoformat(),
        "next_tuesday": tuesday.date().isoformat(),
    }


async def seed_recent_media(session, user, conversation) -> None:
    image_metadata = {
        "file_id": "bench-recent-file",
        "file_unique_id": "bench-recent-serial",
        "mime_type": "image/png",
        "file_size": len(benchmark_png()),
        "source": "attached",
        "telegram_message_id": 800001,
    }
    session.add(Message(
        conversation_id=conversation.id,
        user_id=user.id,
        role=MessageRole.USER,
        content="[image] benchmark serial sticker",
        char_count=32,
        metadata_={"images": [image_metadata], "media_context": SERIAL_MEDIA_CONTEXT},
        content_json={"text": "", "images": [image_metadata], "media_context": SERIAL_MEDIA_CONTEXT},
    ))
    await session.flush()


def benchmark_cases() -> list[BenchCase]:
    return [
        BenchCase(
            id="en_calendar_next_monday",
            text="what schedule i have for next monday?",
            app_locale="en",
        ),
        BenchCase(
            id="ru_calendar_followup_tuesday",
            text="а на следующий вторник?",
            app_locale="ru",
        ),
        BenchCase(
            id="it_calendar_next_tuesday",
            text="Che appuntamenti ho martedì prossimo?",
            app_locale="en",
        ),
        BenchCase(
            id="ru_generic_small",
            text="Коротко объясни, зачем нужен фокус на одной задаче.",
            app_locale="ru",
        ),
        BenchCase(
            id="ru_task_create",
            text="Добавь задачу завтра в 10 проверить latency progress",
            app_locale="ru",
        ),
        BenchCase(
            id="recent_media_unrelated_calendar",
            text="what schedule i have for next monday?",
            app_locale="en",
            media_setup="recent",
        ),
        BenchCase(
            id="recent_media_explicit_followup",
            text="send only what is marked in red",
            app_locale="en",
            media_setup="recent",
        ),
        BenchCase(
            id="attached_image_question",
            text="What is in this image?",
            app_locale="en",
            image=True,
        ),
    ]


def short_reply(text: str, limit: int = 180) -> str:
    compact = " ".join((text or "").split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def quality_verdict(case: BenchCase, llm_kinds: list[str], reply_text: str) -> str:
    lower = reply_text.lower()
    if case.id == "recent_media_unrelated_calendar":
        return "pass" if "media_reference" not in llm_kinds else "fail: media_reference called"
    if case.media_setup == "recent" and "explicit" in case.id:
        return "pass" if "media_reference" in llm_kinds or "focused_vision" in llm_kinds else "check: no media path"
    if case.image:
        return "pass" if "media_understanding" in llm_kinds else "fail: no media_understanding"
    if "calendar" in case.id:
        return "pass" if ("read_calendar_events" in lower or "📅" in reply_text or any(kind == "agent_planner" for kind in llm_kinds)) else "check"
    if "task" in case.id:
        return "pass" if lower else "check"
    return "pass" if reply_text else "check"


async def run_case(
    case: BenchCase,
    *,
    telegram_user_id: int,
    message_id: int,
) -> dict[str, Any]:
    progress_events: list[dict[str, Any]] = []
    started = monotonic()

    async def on_progress(status_text: str) -> None:
        progress_events.append({
            "elapsed_ms": int((monotonic() - started) * 1000),
            "status": str(status_text),
        })

    async def image_loader(metadata: dict) -> ImageInput:
        return ImageInput(
            data=benchmark_png(),
            mime_type=metadata.get("mime_type") or "image/png",
            file_id=metadata.get("file_id") or "bench-recent-file",
            file_unique_id=metadata.get("file_unique_id") or "bench-recent-serial",
            file_size=len(benchmark_png()),
            source="recent",
            telegram_message_id=metadata.get("telegram_message_id"),
        )

    image = None
    if case.image:
        image = ImageInput(
            data=benchmark_png(),
            mime_type="image/png",
            file_id=f"bench-attached-{message_id}",
            file_unique_id=f"bench-attached-{message_id}",
            file_size=len(benchmark_png()),
            source="attached",
            telegram_message_id=message_id,
        )

    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(telegram_user_id, telegram_chat_id=telegram_user_id, language_code=case.app_locale)
        user.locale = case.app_locale
        settings = ensure_language_settings(user.settings)
        settings["reply_language_mode"] = case.reply_language_mode
        settings["reply_language"] = case.reply_language
        user.settings = settings
        conversation = await users.ensure_main_conversation(user)
        if case.media_setup == "recent":
            await seed_recent_media(session, user, conversation)

        orchestrator = AssistantOrchestrator(session)
        result = await orchestrator.handle_user_message(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_user_id,
            telegram_message_id=message_id,
            text=case.text,
            image=image,
            image_loader=image_loader,
            on_progress=on_progress,
            touch_last_seen=False,
        )
        total_ms = int((monotonic() - started) * 1000)
        llm_calls = (
            await session.execute(
                select(LLMCall)
                .where(LLMCall.agent_run_id == result.agent_run_id)
                .order_by(LLMCall.created_at)
            )
        ).scalars().all()
        tool_calls = (
            await session.execute(
                select(ToolCall)
                .where(ToolCall.agent_run_id == result.agent_run_id)
                .order_by(ToolCall.created_at)
            )
        ).scalars().all()
        run = await session.get(AgentRun, result.agent_run_id)

    llm_kinds = [call.request_kind for call in llm_calls]
    return {
        "case_id": case.id,
        "language_mode": case.reply_language_mode,
        "app_locale": case.app_locale,
        "input": case.text,
        "media_setup": "attached_image" if case.image else case.media_setup,
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
            for call in tool_calls
        ],
        "latency_ms": (run.metadata_ or {}).get("latency_ms") if run is not None else {},
        "total_ms": total_ms,
        "first_progress_ms": progress_events[0]["elapsed_ms"] if progress_events else None,
        "reply_text": result.reply_text,
        "reply_short": short_reply(result.reply_text),
        "quality_verdict": quality_verdict(case, llm_kinds, result.reply_text),
    }


def markdown_table(label: str, rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# Assistant Turn Benchmark: {label}",
        "",
        "| case | locale/mode | media | total | first progress | llm calls | quality | reply |",
        "|---|---:|---|---:|---:|---|---|---|",
    ]
    for row in rows:
        total = f"{row['total_ms'] / 1000:.1f}s"
        first = "-" if row["first_progress_ms"] is None else f"{row['first_progress_ms'] / 1000:.1f}s"
        llm = ", ".join(call["request_kind"] for call in row["llm_calls"]) or "-"
        locale = f"{row['app_locale']}/{row['language_mode']}"
        reply = row["reply_short"].replace("|", "\\|")
        lines.append(
            f"| `{row['case_id']}` | {locale} | {row['media_setup']} | {total} | {first} | "
            f"{llm} | {row['quality_verdict']} | {reply} |"
        )
    return "\n".join(lines) + "\n"


def prepare_output_dir(base_dir: str, run_id: str) -> Path:
    out_dir = Path(base_dir).expanduser().resolve() / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="branch", help="Label used in output filenames.")
    parser.add_argument("--out-dir", default="../benchmarks/assistant_turns", help="Output directory.")
    parser.add_argument("--telegram-user-id", type=int, default=None, help="Dedicated benchmark Telegram user id.")
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = prepare_output_dir(args.out_dir, run_id)
    telegram_user_id = args.telegram_user_id or (880000000 + int(time()) % 1000000)
    message_base = int(time()) % 1000000

    async with session_scope() as session:
        user = await UserService(session).ensure_user(
            telegram_user_id,
            telegram_chat_id=telegram_user_id,
            language_code="en",
        )
        dates = await seed_calendar(session, user)

    rows: list[dict[str, Any]] = []
    for index, case in enumerate(benchmark_cases(), start=1):
        row = await run_case(case, telegram_user_id=telegram_user_id, message_id=message_base + index)
        rows.append(row)
        print(json.dumps({
            "case_id": row["case_id"],
            "total_ms": row["total_ms"],
            "llm_calls": [call["request_kind"] for call in row["llm_calls"]],
            "quality_verdict": row["quality_verdict"],
        }, ensure_ascii=False))

    jsonl_path = out_dir / f"{args.label}.jsonl"
    md_path = out_dir / f"{args.label}.md"
    with jsonl_path.open("w", encoding="utf-8") as file:
        file.write(json.dumps({"label": args.label, "telegram_user_id": telegram_user_id, "dates": dates}, ensure_ascii=False) + "\n")
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    md_path.write_text(markdown_table(args.label, rows), encoding="utf-8")
    print(f"\nWrote {jsonl_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    asyncio.run(main())
