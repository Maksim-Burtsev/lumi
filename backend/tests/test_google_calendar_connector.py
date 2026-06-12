from lumi.connectors.google import calendar


def test_google_event_parser_preserves_links_location_and_update_time():
    dto = calendar.calendar_event_dto_from_google_item(
        {
            "id": "evt-1",
            "summary": "Daily",
            "description": "Join notes https://example.com/doc",
            "location": "Meet",
            "htmlLink": "https://calendar.google.com/event?eid=1",
            "hangoutLink": "https://meet.google.com/abc-defg-hij",
            "updated": "2026-06-12T10:00:00Z",
            "status": "confirmed",
            "transparency": "opaque",
            "creator": {"displayName": "Creator", "email": "creator@example.com"},
            "organizer": {"displayName": "Alice", "email": "alice@example.com"},
            "attendees": [
                {
                    "displayName": "Bob",
                    "email": "bob@example.com",
                    "responseStatus": "accepted",
                    "optional": False,
                    "resource": False,
                },
                {
                    "displayName": "Room",
                    "email": "room@example.com",
                    "responseStatus": "needsAction",
                    "optional": True,
                    "resource": True,
                },
                {
                    "displayName": "Me",
                    "email": "me@example.com",
                    "responseStatus": "tentative",
                    "self": True,
                },
            ],
            "start": {"dateTime": "2026-06-12T13:00:00+04:00"},
            "end": {"dateTime": "2026-06-12T13:30:00+04:00"},
        },
        calendar_id="primary",
    )

    assert dto is not None
    assert dto.location == "Meet"
    assert dto.external_url == "https://calendar.google.com/event?eid=1"
    assert dto.meeting_url == "https://meet.google.com/abc-defg-hij"
    assert dto.links == ["https://example.com/doc"]
    assert dto.external_updated_at.isoformat() == "2026-06-12T10:00:00+00:00"
    assert dto.creator == {"name": "Creator", "email": "creator@example.com"}
    assert dto.organizer == {"name": "Alice", "email": "alice@example.com"}
    assert dto.user_response_status == "tentative"
    assert dto.attendees[0]["name"] == "Bob"
    assert dto.attendees[1]["optional"] is True
    assert dto.attendees[1]["resource"] is True
