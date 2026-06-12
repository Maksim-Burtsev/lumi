"""Yandex Calendar connector — read-only via CalDAV (caldav.yandex.ru).

Auth: Yandex login + app password (id.yandex.ru → Безопасность → Пароли приложений
→ «Календарь CalDAV»). Credentials are stored Fernet-encrypted in the connectors table.
The caldav library is sync — every call is wrapped in a thread.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import Connector, ConnectorStatus, ConnectorType, User
from lumi.logging import get_logger
from lumi.security.crypto import CryptoError, decrypt_text, encrypt_text
from lumi.utils.calendar_people import normalize_email, normalize_response_status
from lumi.utils.links import extract_links, prefer_meeting_url

log = get_logger(__name__)

YANDEX_CALDAV_URL = "https://caldav.yandex.ru"


class YandexNotConnectedError(Exception):
    """Raised when Yandex Calendar credentials are absent or unusable."""


@dataclass(slots=True)
class YandexEventDTO:
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
    organizer: dict[str, str] | None = None
    attendees: list[dict[str, object]] | None = None


def _to_utc(value) -> datetime:
    """iCalendar DTSTART/DTEND value (datetime or date) → aware UTC datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    raise ValueError(f"unsupported ical date value: {value!r}")


class YandexCalendarConnector:
    """Read-only CalDAV access. No writes — by design."""

    def __init__(self, username: str, app_password: str, url: str = YANDEX_CALDAV_URL) -> None:
        self._username = username
        self._password = app_password
        self._url = url

    async def verify(self) -> int:
        """Check credentials by listing calendars. Returns calendar count."""
        return await asyncio.to_thread(self._verify_sync)

    def _verify_sync(self) -> int:
        client = self._client()
        try:
            return len(client.principal().calendars())
        finally:
            client.close()

    async def list_events(self, *, start: datetime, end: datetime) -> list[YandexEventDTO]:
        return await asyncio.to_thread(self._list_events_sync, start, end)

    def _client(self):
        import caldav

        return caldav.DAVClient(
            url=self._url, username=self._username, password=self._password
        )

    def _list_events_sync(self, start: datetime, end: datetime) -> list[YandexEventDTO]:
        import caldav

        client = self._client()
        try:
            try:
                calendars = client.principal().calendars()
            except caldav.lib.error.AuthorizationError as exc:
                raise YandexNotConnectedError(
                    "Яндекс отклонил логин/пароль приложения — проверь пароль приложения"
                ) from exc

            events: list[YandexEventDTO] = []
            for calendar in calendars:
                cal_id = str(getattr(calendar, "id", None) or calendar.url)
                try:
                    found = calendar.search(start=start, end=end, event=True, expand=True)
                except Exception as exc:  # noqa: BLE001 — one broken calendar must not kill sync
                    log.warning("yandex calendar search failed",
                                fields={"calendar": cal_id, "error": str(exc)[:200]})
                    continue
                for item in found:
                    events.extend(self._parse_event(item, cal_id))
            return events
        finally:
            client.close()

    @staticmethod
    def _parse_event(item, cal_id: str) -> list[YandexEventDTO]:
        """One caldav object → DTOs (expanded recurrences may hold several VEVENTs)."""
        out: list[YandexEventDTO] = []
        try:
            components = item.icalendar_instance.walk("VEVENT")
        except Exception:  # noqa: BLE001
            return out
        for vevent in components:
            try:
                uid = str(vevent.get("UID", "")) or str(item.url)
                recurrence = vevent.get("RECURRENCE-ID")
                if recurrence is not None:
                    uid = f"{uid}:{recurrence.dt.isoformat()}"
                dtstart = vevent.get("DTSTART")
                if dtstart is None:
                    continue
                start_at = _to_utc(dtstart.dt)
                all_day = not isinstance(dtstart.dt, datetime)
                dtend = vevent.get("DTEND")
                if dtend is not None:
                    end_at = _to_utc(dtend.dt)
                else:
                    end_at = start_at + (timedelta(days=1) if all_day else timedelta(hours=1))
                status = str(vevent.get("STATUS", "CONFIRMED")).lower()
                transp = str(vevent.get("TRANSP", "OPAQUE")).upper()
                description = str(vevent.get("DESCRIPTION", "")) or None
                location = str(vevent.get("LOCATION", "")) or None
                external_url = str(vevent.get("URL", "")) or None
                links = extract_links(description, location, external_url)
                organizer = YandexCalendarConnector._parse_person(vevent.get("ORGANIZER"))
                attendees = [
                    parsed
                    for raw_attendee in YandexCalendarConnector._as_list(vevent.get("ATTENDEE"))
                    if (parsed := YandexCalendarConnector._parse_attendee(raw_attendee)) is not None
                ]
                out.append(
                    YandexEventDTO(
                        external_calendar_id=cal_id,
                        external_event_id=uid,
                        title=str(vevent.get("SUMMARY", "")) or "(без названия)",
                        description=description,
                        start_at=start_at,
                        end_at=end_at,
                        all_day=all_day,
                        busy=transp != "TRANSPARENT",
                        status=status if status in ("confirmed", "tentative", "cancelled") else "confirmed",
                        location=location,
                        meeting_url=prefer_meeting_url(links),
                        external_url=external_url,
                        links=links,
                        organizer=organizer,
                        attendees=attendees,
                    )
                )
            except Exception as exc:  # noqa: BLE001 — skip malformed events
                log.warning("yandex event parse failed", fields={"error": str(exc)[:200]})
        return out

    @staticmethod
    def _as_list(value) -> list:
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    @staticmethod
    def _param(value, name: str):
        params = getattr(value, "params", {}) or {}
        raw = params.get(name)
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        return str(raw) if raw is not None else None

    @staticmethod
    def _parse_person(value) -> dict[str, str] | None:
        if value is None:
            return None
        name = YandexCalendarConnector._param(value, "CN")
        email = normalize_email(value)
        if not name and not email:
            return None
        return {key: val for key, val in {"name": name, "email": email}.items() if val}

    @staticmethod
    def _parse_attendee(value) -> dict[str, object] | None:
        person = YandexCalendarConnector._parse_person(value)
        if person is None:
            return None
        role = (YandexCalendarConnector._param(value, "ROLE") or "").upper()
        attendee: dict[str, object] = {
            **person,
            "response_status": normalize_response_status(
                YandexCalendarConnector._param(value, "PARTSTAT")
            ),
            "optional": role == "OPT-PARTICIPANT",
            "resource": role == "NON-PARTICIPANT",
            "rsvp": (YandexCalendarConnector._param(value, "RSVP") or "").upper() == "TRUE",
        }
        return attendee


# ---------------------------------------------------------------------------
# Credential storage (connectors table, Fernet-encrypted)
# ---------------------------------------------------------------------------

async def get_yandex_connector_row(session: AsyncSession, user: User) -> Connector | None:
    result = await session.execute(
        select(Connector).where(
            Connector.user_id == user.id, Connector.type == ConnectorType.YANDEX
        )
    )
    return result.scalar_one_or_none()


async def save_yandex_credentials(
    session: AsyncSession, user: User, *, username: str, app_password: str
) -> Connector:
    connector = await get_yandex_connector_row(session, user)
    if connector is None:
        connector = Connector(user_id=user.id, type=ConnectorType.YANDEX)
        session.add(connector)
    connector.credentials_encrypted = encrypt_text(
        json.dumps({"username": username, "app_password": app_password})
    )
    connector.status = ConnectorStatus.CONNECTED
    connector.scopes = ["caldav:read"]
    connector.last_error = None
    connector.metadata_ = {**(connector.metadata_ or {}), "username": username}
    await session.flush()
    return connector


async def load_yandex_client(session: AsyncSession, user: User) -> YandexCalendarConnector:
    connector = await get_yandex_connector_row(session, user)
    if connector is None or not connector.credentials_encrypted:
        raise YandexNotConnectedError("Яндекс.Календарь не подключен")
    try:
        creds = json.loads(decrypt_text(connector.credentials_encrypted))
    except (CryptoError, json.JSONDecodeError) as exc:
        raise YandexNotConnectedError(f"не удалось расшифровать креды Яндекса: {exc}") from exc
    return YandexCalendarConnector(creds["username"], creds["app_password"])
