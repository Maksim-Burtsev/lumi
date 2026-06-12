from datetime import UTC, datetime

from lumi.api.serializers import event_to_dict
from lumi.db.models import CalendarEventStatus, CalendarSource
from lumi.db.session import session_scope
from lumi.services.calendar import CalendarService
from lumi.services.users import UserService

from .conftest import TEST_TELEGRAM_ID


def _dt(hour: int) -> datetime:
    return datetime(2026, 6, 12, hour, tzinfo=UTC)


async def test_external_sync_reconciles_missing_events_without_touching_internal(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        calendar = CalendarService(session)
        await calendar.upsert_external_event(
            u,
            source=CalendarSource.YANDEX,
            external_calendar_id="work",
            external_event_id="fresh",
            title="Fresh standup",
            start_at=_dt(9),
            end_at=_dt(10),
        )
        stale = await calendar.upsert_external_event(
            u,
            source=CalendarSource.YANDEX,
            external_calendar_id="work",
            external_event_id="stale",
            title="Moved standup",
            start_at=_dt(10),
            end_at=_dt(11),
        )
        internal = await calendar.create_internal_block(
            u,
            title="Focus",
            start_at=_dt(11),
            end_at=_dt(12),
        )

        cancelled = await calendar.reconcile_external_events(
            u,
            source=CalendarSource.YANDEX,
            external_calendar_id="work",
            start_at=_dt(0),
            end_at=_dt(23),
            seen_event_ids={"fresh"},
        )

        assert cancelled == 1
        assert stale.status == CalendarEventStatus.CANCELLED
        assert internal.status == CalendarEventStatus.CONFIRMED


async def test_event_serializer_exposes_external_details(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        event = await CalendarService(session).upsert_external_event(
            u,
            source=CalendarSource.YANDEX,
            external_calendar_id="work",
            external_event_id="meeting",
            title="Planning",
            start_at=_dt(13),
            end_at=_dt(14),
            description="Agenda https://example.com/doc",
            location="Zoom",
            meeting_url="https://meet.example.com/abc",
            external_url="https://calendar.example.com/event",
            links=[
                "https://meet.example.com/abc",
                "https://calendar.example.com/event",
                "https://example.com/doc",
            ],
            organizer={"name": "Alice", "email": "alice@example.com"},
            attendees=[
                {
                    "name": "Bob",
                    "email": "bob@example.com",
                    "response_status": "accepted",
                    "optional": False,
                    "resource": False,
                },
                {
                    "name": "Room 1",
                    "email": "room@example.com",
                    "response_status": "needsAction",
                    "optional": True,
                    "resource": True,
                },
            ],
            user_response_status="accepted",
        )

        payload = event_to_dict(event)

        assert payload["location"] == "Zoom"
        assert payload["meeting_url"] == "https://meet.example.com/abc"
        assert payload["external_url"] == "https://calendar.example.com/event"
        assert payload["links"] == ["https://example.com/doc"]
        assert payload["last_synced_at"] is not None
        assert payload["organizer"] == {"name": "Alice", "email": "alice@example.com"}
        assert payload["attendee_count"] == 2
        assert payload["user_response_status"] == "accepted"
        assert payload["attendees"][0]["name"] == "Bob"
        assert payload["attendees"][1]["resource"] is True
