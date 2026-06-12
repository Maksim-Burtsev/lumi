"""Text helpers: Telegram chunking, normalization, pluralization."""

from __future__ import annotations

import re

TELEGRAM_MAX_MESSAGE = 4096


def chunk_telegram(text: str, limit: int = TELEGRAM_MAX_MESSAGE) -> list[str]:
    """Split text into Telegram-sized chunks, preferring paragraph/line breaks."""
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    rest = text
    while len(rest) > limit:
        window = rest[:limit]
        cut = window.rfind("\n\n")
        if cut < limit // 2:
            cut = window.rfind("\n")
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        chunks.append(rest)
    return chunks


def normalize_for_match(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation — for dedup/keyword matching."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def keyword_overlap(a: str, b: str) -> float:
    """Jaccard-ish overlap of meaningful words (len >= 3)."""
    words_a = {w for w in normalize_for_match(a).split() if len(w) >= 3}
    words_b = {w for w in normalize_for_match(b).split() if len(w) >= 3}
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / min(len(words_a), len(words_b))


def ru_plural(n: int, one: str, few: str, many: str) -> str:
    """Russian pluralization: 1 задача / 2 задачи / 5 задач."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(suffix)].rstrip() + suffix
