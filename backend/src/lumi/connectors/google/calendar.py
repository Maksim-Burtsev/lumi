"""Google Calendar connector: read events, create events (confirmation-gated upstream)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

from lumi.connectors.google.auth import load_credentials
from lumi.logging import get_logger
from lumi.utils.links import extract_links, prefer_meeting_url

log = get_logger(__name__)


@dataclass(slots=True)
class CalendarEventDTO:
    external_calendar_id: str
    external_event_id: str
    title: str
    description: str | None
    start_at: datetime
    end_at: datetime
    all_day: bool
    busy: bool
    status: str  # confirmed | tentative | cancelled
    location: str | None = None
    meeting_url: str | None = None
    external_url: str | None = None
    links: list[str] | None = None
    external_updated_at: datetime | None = None


@dataclass(slots=True)
class ExternalEventRef:
    external_calendar_id: str
    external_event_id: str
    html_link: str | None


def _parse_when(when: dict[str, Any]) -> tuple[datetime, bool]:
    if "dateTime" in when:
        return datetime.fromisoformat(when["dateTime"]), False
    # All-day events carry a bare date.
    day = date.fromisoformat(when["date"])
    return datetime.combine(day, time.min, tzinfo=UTC), True


def _parse_google_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _conference_link(item: dict[str, Any]) -> str | None:
    if item.get("hangoutLink"):
        return item["hangoutLink"]
    for entry in (item.get("conferenceData") or {}).get("entryPoints") or []:
        uri = entry.get("uri")
        if uri:
            return uri
    return None


def calendar_event_dto_from_google_item(
    item: dict[str, Any], *, calendar_id: str
) -> CalendarEventDTO | None:
    try:
        start_at, all_day = _parse_when(item["start"])
        end_at, _ = _parse_when(item["end"])
    except (KeyError, ValueError):
        return None
    meeting_url = _conference_link(item)
    external_url = item.get("htmlLink")
    links = extract_links(item.get("description"), item.get("location"))
    return CalendarEventDTO(
        external_calendar_id=calendar_id,
        external_event_id=item["id"],
        title=item.get("summary") or "(без названия)",
        description=item.get("description"),
        start_at=start_at,
        end_at=end_at,
        all_day=all_day,
        busy=item.get("transparency", "opaque") != "transparent",
        status=item.get("status", "confirmed"),
        location=item.get("location"),
        meeting_url=meeting_url or prefer_meeting_url(links),
        external_url=external_url,
        links=links,
        external_updated_at=_parse_google_datetime(item.get("updated")),
    )


class GoogleCalendarConnector:
    async def list_events(
        self, *, start: datetime, end: datetime, calendar_id: str = "primary", max_results: int = 250
    ) -> list[CalendarEventDTO]:
        creds = await load_credentials()
        return await asyncio.to_thread(
            self._list_events_sync, creds, start, end, calendar_id, max_results
        )

    def _list_events_sync(
        self, creds, start: datetime, end: datetime, calendar_id: str, max_results: int
    ) -> list[CalendarEventDTO]:
        from googleapiclient.discovery import build

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=max_results,
            )
            .execute()
        )
        events: list[CalendarEventDTO] = []
        for item in response.get("items", []):
            if item.get("status") == "cancelled":
                continue
            dto = calendar_event_dto_from_google_item(item, calendar_id=calendar_id)
            if dto is not None:
                events.append(dto)
        return events

    async def watch_events(
        self,
        *,
        address: str,
        channel_id: str,
        token: str,
        calendar_id: str = "primary",
        ttl_seconds: int = 604800,
    ) -> dict[str, Any]:
        creds = await load_credentials()
        return await asyncio.to_thread(
            self._watch_events_sync, creds, address, channel_id, token, calendar_id, ttl_seconds
        )

    def _watch_events_sync(
        self, creds, address: str, channel_id: str, token: str, calendar_id: str, ttl_seconds: int
    ) -> dict[str, Any]:
        from googleapiclient.discovery import build

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return (
            service.events()
            .watch(
                calendarId=calendar_id,
                body={
                    "id": channel_id,
                    "type": "web_hook",
                    "address": address,
                    "token": token,
                    "params": {"ttl": str(ttl_seconds)},
                },
            )
            .execute()
        )

    async def create_event(
        self,
        *,
        title: str,
        start_at: datetime,
        end_at: datetime,
        description: str | None = None,
        timezone: str = "Europe/Moscow",
        calendar_id: str = "primary",
    ) -> ExternalEventRef:
        creds = await load_credentials()
        return await asyncio.to_thread(
            self._create_event_sync, creds, title, start_at, end_at, description, timezone, calendar_id
        )

    def _create_event_sync(
        self, creds, title: str, start_at: datetime, end_at: datetime,
        description: str | None, timezone: str, calendar_id: str,
    ) -> ExternalEventRef:
        from googleapiclient.discovery import build

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        body = {
            "summary": title,
            "description": description or "Создано Lumi",
            "start": {"dateTime": start_at.isoformat(), "timeZone": timezone},
            "end": {"dateTime": end_at.isoformat(), "timeZone": timezone},
        }
        created = service.events().insert(calendarId=calendar_id, body=body).execute()
        return ExternalEventRef(
            external_calendar_id=calendar_id,
            external_event_id=created["id"],
            html_link=created.get("htmlLink"),
        )
