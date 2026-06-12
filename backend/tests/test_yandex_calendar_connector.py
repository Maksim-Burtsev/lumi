from icalendar import Calendar

from lumi.connectors.yandex.caldav_client import YandexCalendarConnector


class CaldavItem:
    def __init__(self, ics: str) -> None:
        self.icalendar_instance = Calendar.from_ical(ics)
        self.url = "https://caldav.example/events/1.ics"


def test_yandex_event_parser_preserves_organizer_and_attendees():
    item = CaldavItem(
        """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1
SUMMARY:Daily
DTSTART:20260612T090000Z
DTEND:20260612T093000Z
ORGANIZER;CN=Alice:mailto:alice@example.com
ATTENDEE;CN=Bob;PARTSTAT=ACCEPTED;ROLE=REQ-PARTICIPANT:mailto:bob@example.com
ATTENDEE;CN=Carol;PARTSTAT=NEEDS-ACTION;ROLE=OPT-PARTICIPANT;RSVP=TRUE:mailto:carol@example.com
DESCRIPTION:Ссылка на видеовстречу: https://telemost.yandex.ru/j/123
LOCATION:Zoom
URL:https://calendar.yandex.com/event/1
END:VEVENT
END:VCALENDAR
"""
    )

    events = YandexCalendarConnector._parse_event(item, "work")

    assert len(events) == 1
    event = events[0]
    assert event.organizer == {"name": "Alice", "email": "alice@example.com"}
    assert event.attendees[0]["name"] == "Bob"
    assert event.attendees[0]["response_status"] == "accepted"
    assert event.attendees[1]["name"] == "Carol"
    assert event.attendees[1]["response_status"] == "needsAction"
    assert event.attendees[1]["optional"] is True
    assert event.attendees[1]["rsvp"] is True
