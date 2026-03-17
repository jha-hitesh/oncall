from unittest import mock

import pytest
from bs4 import BeautifulSoup
from django.urls import reverse
from django.utils.datastructures import MultiValueDict
from django.utils.http import urlencode
from rest_framework.test import APIClient

from apps.base.models import UserNotificationPolicy
from apps.twilioapp.models import TwilioCallStatuses, TwilioPhoneCall


@pytest.fixture
def make_twilio_phone_call(
    make_organization_and_user,
    make_alert_receive_channel,
    make_user_notification_policy,
    make_alert_group,
    make_phone_call_record,
    make_alert,
):
    organization, user = make_organization_and_user()
    alert_receive_channel = make_alert_receive_channel(organization)
    alert_group = make_alert_group(alert_receive_channel)
    make_alert(alert_group, raw_request_data="{}")
    notification_policy = make_user_notification_policy(
        user=user,
        step=UserNotificationPolicy.Step.NOTIFY,
        notify_by=UserNotificationPolicy.NotificationChannel.PHONE_CALL,
    )
    phone_call_record = make_phone_call_record(
        receiver=user,
        represents_alert_group=alert_group,
        notification_policy=notification_policy,
    )
    return TwilioPhoneCall.objects.create(sid="SMa12312312a123a123123c6dd2f1aee77", phone_call_record=phone_call_record)


@pytest.mark.django_db
def test_forbidden_requests(make_twilio_phone_call):
    """Tests check inaccessibility of twilio urls for unauthorized requests"""
    twilio_phone_call = make_twilio_phone_call

    # empty data case
    data = {}

    client = APIClient()
    response = client.post(
        reverse("twilioapp:call_status_events"),
        data=urlencode(MultiValueDict(data), doseq=True),
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status_code == 403
    assert response.data["detail"] == "You do not have permission to perform this action."

    # wrong AccountSid data
    data = {"CallSid": twilio_phone_call.sid, "CallStatus": "completed", "AccountSid": "TopSecretAccountSid"}

    client = APIClient()
    response = client.post(
        path=reverse("twilioapp:call_status_events"),
        data=urlencode(MultiValueDict(data), doseq=True),
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status_code == 403
    assert response.data["detail"] == "You do not have permission to perform this action."

    # absent CallSid data
    data = {"CallStatus": "completed", "AccountSid": "TopSecretAccountSid"}

    client = APIClient()
    response = client.post(
        path=reverse("twilioapp:call_status_events"),
        data=urlencode(MultiValueDict(data), doseq=True),
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status_code == 403
    assert response.data["detail"] == "You do not have permission to perform this action."


@mock.patch("apps.twilioapp.views.AllowOnlyTwilio.has_permission")
@pytest.mark.django_db
def test_update_status(mock_has_permission, make_twilio_phone_call):
    """The test for PhoneCall status update via api"""
    twilio_phone_call = make_twilio_phone_call

    mock_has_permission.return_value = True

    for status in ["in-progress", "completed", "busy", "failed", "no-answer", "canceled"]:
        data = {
            "CallSid": twilio_phone_call.sid,
            "CallStatus": status,
            "AccountSid": "Because of mock_has_permission there are may be any value",
        }

        client = APIClient()
        response = client.post(
            path=reverse("twilioapp:call_status_events"),
            data=urlencode(MultiValueDict(data), doseq=True),
            content_type="application/x-www-form-urlencoded",
        )

        assert response.status_code == 204
        assert response.data == ""

        twilio_phone_call.refresh_from_db()
        assert twilio_phone_call.status == TwilioCallStatuses.DETERMINANT[status]


@mock.patch("apps.twilioapp.views.AllowOnlyTwilio.has_permission")
@mock.patch("apps.twilioapp.gather.get_gather_url")
@mock.patch("apps.twilioapp.gather.live_settings")
@pytest.mark.django_db
def test_acknowledge_by_phone(mock_live_settings, mock_has_permission, mock_get_gather_url, make_twilio_phone_call):
    twilio_phone_call = make_twilio_phone_call
    alert_group = twilio_phone_call.phone_call_record.represents_alert_group
    mock_has_permission.return_value = True
    mock_get_gather_url.return_value = reverse("twilioapp:gather")
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {
        "acknowledge_button": "1",
        "resolve_button": "2",
        "silence_button": "3",
    }
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_TEMPLATE = None

    data = {
        "CallSid": twilio_phone_call.sid,
        "Digits": "1",
        "AccountSid": "Because of mock_has_permission there are may be any value",
    }

    assert alert_group.acknowledged is False

    client = APIClient()
    response = client.post(
        reverse("twilioapp:gather"),
        data=urlencode(MultiValueDict(data), doseq=True),
        content_type="application/x-www-form-urlencoded",
    )

    content = response.content.decode("utf-8")

    assert response.status_code == 200
    assert "Acknowledged" in content

    alert_group.refresh_from_db()
    assert alert_group.acknowledged is True


@mock.patch("apps.twilioapp.views.AllowOnlyTwilio.has_permission")
@mock.patch("apps.twilioapp.gather.get_gather_url")
@mock.patch("apps.twilioapp.gather.live_settings")
@pytest.mark.django_db
def test_resolve_by_phone(mock_live_settings, mock_has_permission, mock_get_gather_url, make_twilio_phone_call):
    twilio_phone_call = make_twilio_phone_call

    mock_has_permission.return_value = True
    mock_get_gather_url.return_value = reverse("twilioapp:gather")
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {
        "acknowledge_button": "1",
        "resolve_button": "2",
        "silence_button": "3",
    }
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_TEMPLATE = None

    data = {
        "CallSid": twilio_phone_call.sid,
        "Digits": "2",
        "AccountSid": "Because of mock_has_permission there are may be any value",
    }

    alert_group = twilio_phone_call.phone_call_record.represents_alert_group
    assert alert_group.resolved is False

    client = APIClient()
    response = client.post(
        reverse("twilioapp:gather"),
        data=urlencode(MultiValueDict(data), doseq=True),
        content_type="application/x-www-form-urlencoded",
    )

    content = response.content.decode("utf-8")
    content = BeautifulSoup(content, features="xml").findAll(string=True)

    assert response.status_code == 200
    assert "Resolved" in content

    alert_group.refresh_from_db()
    assert alert_group.resolved is True


@mock.patch("apps.twilioapp.views.AllowOnlyTwilio.has_permission")
@mock.patch("apps.twilioapp.gather.get_gather_url")
@mock.patch("apps.twilioapp.gather.live_settings")
@pytest.mark.django_db
def test_silence_by_phone(mock_live_settings, mock_has_permission, mock_get_gather_url, make_twilio_phone_call):
    twilio_phone_call = make_twilio_phone_call

    mock_has_permission.return_value = True
    mock_get_gather_url.return_value = reverse("twilioapp:gather")
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {
        "acknowledge_button": "1",
        "resolve_button": "2",
        "silence_button": "3",
    }
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_TEMPLATE = None

    data = {
        "CallSid": twilio_phone_call.sid,
        "Digits": "3",
        "AccountSid": "Because of mock_has_permission there are may be any value",
    }

    alert_group = twilio_phone_call.phone_call_record.represents_alert_group
    assert alert_group.resolved is False

    client = APIClient()
    response = client.post(
        reverse("twilioapp:gather"),
        data=urlencode(MultiValueDict(data), doseq=True),
        content_type="application/x-www-form-urlencoded",
    )

    content = response.content.decode("utf-8")

    assert response.status_code == 200
    assert "Silenced" in content

    alert_group.refresh_from_db()
    assert alert_group.silenced_until is not None


@mock.patch("apps.twilioapp.views.AllowOnlyTwilio.has_permission")
@mock.patch("apps.twilioapp.gather.get_gather_url")
@mock.patch("apps.twilioapp.gather.AlertGroupPhoneCallRenderer.render")
@mock.patch("apps.twilioapp.gather.live_settings")
@pytest.mark.django_db
def test_repeat_message_by_phone(
    mock_live_settings, mock_render, mock_get_gather_url, mock_has_permission, make_twilio_phone_call
):
    twilio_phone_call = make_twilio_phone_call

    mock_has_permission.return_value = True
    mock_get_gather_url.return_value = reverse("twilioapp:gather")
    mock_render.return_value = "Repeated phone call message"
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {
        "acknowledge_button": "1",
        "resolve_button": "2",
        "silence_button": "3",
        "repeat_button": "4",
        "wait_time_for_user_action": 5,
    }
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_TEMPLATE = (
        "Press {acknowledge_button} to acknowledge, {resolve_button} to resolve, "
        "{silence_button} to silence for {silence_in_minutes} minutes and "
        "{repeat_button} to repeat this message"
    )

    data = {
        "CallSid": twilio_phone_call.sid,
        "Digits": "4",
        "AccountSid": "Because of mock_has_permission there are may be any value",
    }

    client = APIClient()
    response = client.post(
        reverse("twilioapp:gather"),
        data=urlencode(MultiValueDict(data), doseq=True),
        content_type="application/x-www-form-urlencoded",
    )

    content = response.content.decode("utf-8")
    content = BeautifulSoup(content, features="xml").findAll(string=True)

    assert response.status_code == 200
    assert "Repeated phone call message" in content
    assert any("Press 1 to acknowledge" in line and "4 to repeat this message" in line for line in content)


@mock.patch("apps.twilioapp.views.AllowOnlyTwilio.has_permission")
@mock.patch("apps.twilioapp.gather.get_gather_url")
@mock.patch("apps.twilioapp.gather.live_settings")
@pytest.mark.django_db
def test_custom_phone_call_instruction_config(
    mock_live_settings, mock_get_gather_url, mock_has_permission, make_twilio_phone_call
):
    twilio_phone_call = make_twilio_phone_call
    alert_group = twilio_phone_call.phone_call_record.represents_alert_group

    mock_has_permission.return_value = True
    mock_get_gather_url.return_value = reverse("twilioapp:gather")
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {
        "acknowledge_button": "7",
        "resolve_button": "8",
        "silence_button": "9",
        "repeat_button": "6",
        "acknowledge_message": "Incident acknowledged",
        "silence_in_minutes": 45,
        "wait_time_for_user_action": 11,
    }
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_TEMPLATE = (
        "Press {acknowledge_button} to ack, {resolve_button} to resolve, "
        "{silence_button} to snooze for {silence_in_minutes} minutes and "
        "{repeat_button} to replay"
    )

    response = APIClient().post(
        reverse("twilioapp:gather"),
        data=urlencode(
            MultiValueDict(
                {
                    "CallSid": twilio_phone_call.sid,
                    "Digits": "7",
                    "AccountSid": "Because of mock_has_permission there are may be any value",
                }
            ),
            doseq=True,
        ),
        content_type="application/x-www-form-urlencoded",
    )

    content = response.content.decode("utf-8")

    assert response.status_code == 200
    assert "Incident acknowledged" in content

    alert_group.refresh_from_db()
    assert alert_group.acknowledged is True

    instruction_response = APIClient().post(
        reverse("twilioapp:gather"),
        data=urlencode(
            MultiValueDict(
                {
                    "CallSid": twilio_phone_call.sid,
                    "Digits": "0",
                    "AccountSid": "Because of mock_has_permission there are may be any value",
                }
            ),
            doseq=True,
        ),
        content_type="application/x-www-form-urlencoded",
    )

    instruction_content = BeautifulSoup(instruction_response.content.decode("utf-8"), features="xml").findAll(
        string=True
    )

    assert any(
        "Press 7 to ack, 8 to resolve, 9 to snooze for 45 minutes and 6 to replay" in line
        for line in instruction_content
    )


@mock.patch("apps.twilioapp.views.AllowOnlyTwilio.has_permission")
@mock.patch("apps.twilioapp.gather.get_gather_url")
@mock.patch("apps.twilioapp.gather.live_settings")
@pytest.mark.django_db
def test_action_success_messages_fall_back_to_defaults(
    mock_live_settings, mock_get_gather_url, mock_has_permission, make_twilio_phone_call
):
    twilio_phone_call = make_twilio_phone_call

    mock_has_permission.return_value = True
    mock_get_gather_url.return_value = reverse("twilioapp:gather")
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {
        "acknowledge_button": "1",
        "resolve_button": "2",
        "silence_button": "3",
        "resolve_message": "Incident resolved",
    }
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_TEMPLATE = None

    acknowledge_response = APIClient().post(
        reverse("twilioapp:gather"),
        data=urlencode(
            MultiValueDict(
                {
                    "CallSid": twilio_phone_call.sid,
                    "Digits": "1",
                    "AccountSid": "Because of mock_has_permission there are may be any value",
                }
            ),
            doseq=True,
        ),
        content_type="application/x-www-form-urlencoded",
    )
    resolve_response = APIClient().post(
        reverse("twilioapp:gather"),
        data=urlencode(
            MultiValueDict(
                {
                    "CallSid": twilio_phone_call.sid,
                    "Digits": "2",
                    "AccountSid": "Because of mock_has_permission there are may be any value",
                }
            ),
            doseq=True,
        ),
        content_type="application/x-www-form-urlencoded",
    )
    silence_response = APIClient().post(
        reverse("twilioapp:gather"),
        data=urlencode(
            MultiValueDict(
                {
                    "CallSid": twilio_phone_call.sid,
                    "Digits": "3",
                    "AccountSid": "Because of mock_has_permission there are may be any value",
                }
            ),
            doseq=True,
        ),
        content_type="application/x-www-form-urlencoded",
    )

    assert "Acknowledged" in acknowledge_response.content.decode("utf-8")
    assert "Incident resolved" in resolve_response.content.decode("utf-8")
    assert "Silenced" in silence_response.content.decode("utf-8")


@mock.patch("apps.twilioapp.views.AllowOnlyTwilio.has_permission")
@mock.patch("apps.twilioapp.gather.get_gather_url")
@mock.patch("apps.twilioapp.gather.live_settings")
@pytest.mark.django_db
def test_phone_call_instruction_config_allows_star_and_hash_buttons(
    mock_live_settings, mock_get_gather_url, mock_has_permission, make_twilio_phone_call
):
    twilio_phone_call = make_twilio_phone_call

    mock_has_permission.return_value = True
    mock_get_gather_url.return_value = reverse("twilioapp:gather")
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {
        "acknowledge_button": "*",
        "resolve_button": "#",
        "silence_button": "9",
        "wait_time_for_user_action": 5,
    }
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_TEMPLATE = None

    acknowledge_response = APIClient().post(
        reverse("twilioapp:gather"),
        data=urlencode(
            MultiValueDict(
                {
                    "CallSid": twilio_phone_call.sid,
                    "Digits": "*",
                    "AccountSid": "Because of mock_has_permission there are may be any value",
                }
            ),
            doseq=True,
        ),
        content_type="application/x-www-form-urlencoded",
    )

    assert acknowledge_response.status_code == 200
    assert "Acknowledged" in acknowledge_response.content.decode("utf-8")

    instruction_response = APIClient().post(
        reverse("twilioapp:gather"),
        data=urlencode(
            MultiValueDict(
                {
                    "CallSid": twilio_phone_call.sid,
                    "Digits": "0",
                    "AccountSid": "Because of mock_has_permission there are may be any value",
                }
            ),
            doseq=True,
        ),
        content_type="application/x-www-form-urlencoded",
    )

    instruction_content = BeautifulSoup(instruction_response.content.decode("utf-8"), features="xml").findAll(
        string=True
    )

    assert any(
        "Press * to acknowledge, # to resolve, 9 to silence for 30 minutes and 0 to repeat this message" in line
        for line in instruction_content
    )


@mock.patch("apps.twilioapp.views.AllowOnlyTwilio.has_permission")
@mock.patch("apps.twilioapp.gather.get_gather_url")
@mock.patch("apps.twilioapp.gather.live_settings")
@pytest.mark.django_db
def test_invalid_buttons_disable_optional_actions(
    mock_live_settings, mock_get_gather_url, mock_has_permission, make_twilio_phone_call
):
    twilio_phone_call = make_twilio_phone_call

    mock_has_permission.return_value = True
    mock_get_gather_url.return_value = reverse("twilioapp:gather")
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {
        "acknowledge_button": "1",
        "resolve_button": "x",
        "silence_button": None,
        "repeat_button": "repeat",
    }
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_TEMPLATE = None

    response = APIClient().post(
        reverse("twilioapp:gather"),
        data=urlencode(
            MultiValueDict(
                {
                    "CallSid": twilio_phone_call.sid,
                    "Digits": "2",
                    "AccountSid": "Because of mock_has_permission there are may be any value",
                }
            ),
            doseq=True,
        ),
        content_type="application/x-www-form-urlencoded",
    )

    content = BeautifulSoup(response.content.decode("utf-8"), features="xml").findAll(string=True)

    assert response.status_code == 200
    assert "Wrong digit" in content
    assert any("Press 1 to acknowledge" in line for line in content)
    assert all("resolve" not in line for line in content)
    assert all("silence" not in line for line in content)
    assert all("repeat this message" not in line for line in content)


@mock.patch("apps.twilioapp.gather.live_settings")
def test_get_phone_call_wait_time_for_user_action_from_config(mock_live_settings):
    from apps.twilioapp.gather import get_phone_call_wait_time_for_user_action

    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {"acknowledge_button": "1", "wait_time_for_user_action": 9}

    assert get_phone_call_wait_time_for_user_action() == 9


@mock.patch("apps.twilioapp.gather.live_settings")
def test_get_phone_call_wait_time_for_user_action_falls_back_to_default(mock_live_settings):
    from apps.twilioapp.gather import get_phone_call_wait_time_for_user_action

    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {"acknowledge_button": "1", "wait_time_for_user_action": "x"}

    assert get_phone_call_wait_time_for_user_action() == 5


@mock.patch("apps.twilioapp.gather.live_settings")
def test_get_phone_call_silence_in_minutes_falls_back_to_default(mock_live_settings):
    from apps.twilioapp.gather import get_phone_call_silence_in_minutes

    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {"acknowledge_button": "1"}

    assert get_phone_call_silence_in_minutes() == 30


@mock.patch("apps.twilioapp.gather.live_settings")
def test_get_phone_call_silence_in_minutes_from_config(mock_live_settings):
    from apps.twilioapp.gather import get_phone_call_silence_in_minutes

    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {"acknowledge_button": "1", "silence_in_minutes": 60}

    assert get_phone_call_silence_in_minutes() == 60


@mock.patch("apps.twilioapp.gather.live_settings")
def test_default_instructions_template_uses_enabled_actions(mock_live_settings):
    from apps.twilioapp.gather import get_alert_group_gather_instructions

    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {
        "acknowledge_button": "1",
        "resolve_button": "2",
        "silence_button": "bad",
        "repeat_button": "4",
    }
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_TEMPLATE = None

    instructions = get_alert_group_gather_instructions()

    assert instructions == "Press 1 to acknowledge, 2 to resolve and 4 to repeat this message"


@mock.patch("apps.twilioapp.gather.live_settings")
def test_default_instructions_template_with_acknowledge_only(mock_live_settings):
    from apps.twilioapp.gather import get_alert_group_gather_instructions

    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {
        "acknowledge_button": "1",
        "resolve_button": None,
        "silence_button": None,
        "repeat_button": None,
    }
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_TEMPLATE = None

    instructions = get_alert_group_gather_instructions()

    assert instructions == "Press 1 to acknowledge"


@mock.patch("apps.twilioapp.gather.live_settings")
def test_custom_template_can_use_empty_disabled_optional_buttons(mock_live_settings):
    from apps.twilioapp.gather import get_alert_group_gather_instructions

    mock_live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG = {"acknowledge_button": "1", "repeat_button": None}
    mock_live_settings.PHONE_CALL_INSTRUCTIONS_TEMPLATE = "Ack {acknowledge_button}; Repeat {repeat_button}"

    instructions = get_alert_group_gather_instructions()

    assert instructions == "Ack 1; Repeat "


@mock.patch("apps.twilioapp.views.AllowOnlyTwilio.has_permission")
@mock.patch("apps.twilioapp.gather.get_gather_url")
@pytest.mark.django_db
def test_wrong_pressed_digit(mock_has_permission, mock_get_gather_url, make_twilio_phone_call):
    twilio_phone_call = make_twilio_phone_call

    mock_has_permission.return_value = True
    mock_get_gather_url.return_value = reverse("twilioapp:gather")

    data = {
        "CallSid": twilio_phone_call.sid,
        "Digits": "0",
        "AccountSid": "Because of mock_has_permission there are may be any value",
    }

    client = APIClient()
    response = client.post(
        path=reverse("twilioapp:gather"),
        data=urlencode(MultiValueDict(data), doseq=True),
        content_type="application/x-www-form-urlencoded",
    )

    content = response.content.decode("utf-8")
    content = BeautifulSoup(content, features="xml").findAll(string=True)

    assert response.status_code == 200
    assert "Wrong digit" in content
