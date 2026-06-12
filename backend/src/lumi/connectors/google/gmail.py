"""Gmail read-only connector. Sync Google client wrapped in threads."""

from __future__ import annotations

import asyncio
import base64
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from lumi.connectors.google.auth import load_credentials
from lumi.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class EmailMessageDTO:
    external_message_id: str
    sender: str | None
    recipients: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    subject: str | None = None
    snippet: str | None = None
    body_text: str | None = None
    date_at: datetime | None = None


@dataclass(slots=True)
class EmailThreadDTO:
    external_thread_id: str
    subject: str | None
    participants: list[str]
    labels: list[str]
    snippet: str | None
    last_message_at: datetime | None
    messages: list[EmailMessageDTO] = field(default_factory=list)


def _header(headers: list[dict], name: str) -> str | None:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _decode_body(payload: dict) -> str | None:
    """Extract a text/plain body from a Gmail message payload (best effort)."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            try:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            except (ValueError, TypeError):
                return None
    for part in payload.get("parts", []) or []:
        text = _decode_body(part)
        if text:
            return text
    return None


def _split_addresses(value: str | None) -> list[str]:
    if not value:
        return []
    return [a.strip() for a in re.split(r"[,;]", value) if a.strip()]


class GmailConnector:
    """Read-only Gmail access for triage. No send/delete/archive — by design."""

    async def list_recent_threads(
        self, *, since: datetime, max_results: int = 50, include_bodies: bool = False
    ) -> list[EmailThreadDTO]:
        creds = await load_credentials()
        return await asyncio.to_thread(
            self._list_recent_threads_sync, creds, since, max_results, include_bodies
        )

    def _list_recent_threads_sync(
        self, creds, since: datetime, max_results: int, include_bodies: bool
    ) -> list[EmailThreadDTO]:
        from googleapiclient.discovery import build

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        query = f"after:{int(since.timestamp())} in:inbox"
        listing = (
            service.users()
            .threads()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        threads: list[EmailThreadDTO] = []
        for item in listing.get("threads", []):
            thread_id = item["id"]
            detail = (
                service.users()
                .threads()
                .get(
                    userId="me",
                    id=thread_id,
                    format="full" if include_bodies else "metadata",
                    metadataHeaders=["From", "To", "Cc", "Subject", "Date"],
                )
                .execute()
            )
            messages: list[EmailMessageDTO] = []
            labels: set[str] = set()
            participants: set[str] = set()
            last_message_at: datetime | None = None
            subject: str | None = None

            for msg in detail.get("messages", []):
                payload = msg.get("payload", {})
                headers = payload.get("headers", [])
                sender = _header(headers, "From")
                msg_subject = _header(headers, "Subject")
                date_at = _parse_date(_header(headers, "Date"))
                if msg_subject and not subject:
                    subject = msg_subject
                if sender:
                    participants.add(sender)
                for addr in _split_addresses(_header(headers, "To")):
                    participants.add(addr)
                labels.update(msg.get("labelIds", []))
                if date_at and (last_message_at is None or date_at > last_message_at):
                    last_message_at = date_at
                messages.append(
                    EmailMessageDTO(
                        external_message_id=msg["id"],
                        sender=sender,
                        recipients=_split_addresses(_header(headers, "To")),
                        cc=_split_addresses(_header(headers, "Cc")),
                        subject=msg_subject,
                        snippet=msg.get("snippet"),
                        body_text=_decode_body(payload) if include_bodies else None,
                        date_at=date_at,
                    )
                )

            threads.append(
                EmailThreadDTO(
                    external_thread_id=thread_id,
                    subject=subject,
                    participants=sorted(participants),
                    labels=sorted(labels),
                    snippet=detail.get("messages", [{}])[-1].get("snippet") if detail.get("messages") else None,
                    last_message_at=last_message_at,
                    messages=messages,
                )
            )
        return threads
