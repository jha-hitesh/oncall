from unittest.mock import Mock, patch

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.google.client import GoogleCalendarAPIClient


@pytest.mark.django_db
@override_settings(
    SOCIAL_AUTH_GOOGLE_OAUTH2_KEY="google-key",
    SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET="google-secret",
)
@patch("apps.google.client.build")
def test_create_event(mock_build):
    mock_service = Mock()
    mock_build.return_value = mock_service

    expected_response = {
        "id": "event-1",
        "htmlLink": "https://calendar.google.com/event",
        "hangoutLink": "https://meet.google.com/abc-defg-hij",
    }

    mock_service.events.return_value.insert.return_value.execute.return_value = expected_response

    client = GoogleCalendarAPIClient("access-token", "refresh-token")

    start = timezone.now()
    end = start + timezone.timedelta(hours=1)
    response = client.create_event(
        summary="INC-1234 War Room",
        description="Incident bridge for INC-1234",
        start=start,
        end=end,
        attendees=["a@company.com", "b@company.com"],
    )

    assert response == expected_response

    insert_kwargs = mock_service.events.return_value.insert.call_args.kwargs
    assert insert_kwargs["calendarId"] == "primary"
    assert insert_kwargs["conferenceDataVersion"] == 1
    assert insert_kwargs["sendUpdates"] == "all"
    assert insert_kwargs["body"]["summary"] == "INC-1234 War Room"
    assert insert_kwargs["body"]["description"] == "Incident bridge for INC-1234"
    assert insert_kwargs["body"]["attendees"] == [{"email": "a@company.com"}, {"email": "b@company.com"}]
    assert insert_kwargs["body"]["conferenceData"]["createRequest"]["conferenceSolutionKey"]["type"] == "hangoutsMeet"
