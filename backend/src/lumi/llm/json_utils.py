"""Robust JSON extraction from LLM output."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object out of arbitrary LLM output.

    Strategy: strip markdown fences → try direct parse → fall back to the
    first balanced ``{...}`` substring. Raises ValueError when nothing parses.
    """
    if not text or not text.strip():
        raise ValueError("empty LLM output")

    cleaned = _FENCE_RE.sub("", text.strip()).strip()

    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Find the first balanced JSON object, respecting strings/escapes.
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start : i + 1]
                    try:
                        result = json.loads(candidate)
                        if isinstance(result, dict):
                            return result
                    except json.JSONDecodeError:
                        break  # try the next opening brace
        start = cleaned.find("{", start + 1)

    raise ValueError(f"no parseable JSON object in LLM output ({len(text)} chars)")
