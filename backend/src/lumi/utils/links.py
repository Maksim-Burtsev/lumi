"""Small URL helpers used by calendar connectors and serializers."""

from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_TRAILING = ".,;:!?)]}'\""


def extract_links(*texts: str | None) -> list[str]:
    """Return unique URLs in encounter order, with common punctuation stripped."""
    links: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in _URL_RE.findall(text):
            url = match.rstrip(_TRAILING)
            if url and url not in seen:
                links.append(url)
                seen.add(url)
    return links


def prefer_meeting_url(links: list[str]) -> str | None:
    """Pick the most likely join URL from extracted event links."""
    for link in links:
        lowered = link.lower()
        if any(marker in lowered for marker in ("meet.", "zoom.", "telemost", "teams.")):
            return link
    return links[0] if links else None
