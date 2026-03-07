import logging

from django.urls import reverse
from twilio.twiml.voice_response import Gather, VoiceResponse

from apps.alerts.constants import ActionSource
from apps.alerts.incident_appearance.renderers.phone_call_renderer import AlertGroupPhoneCallRenderer
from apps.twilioapp.models import TwilioPhoneCall
from common.api_helpers.utils import create_engine_url
from settings.base import PHONE_CALL_ALLOWED_REPEAT_MESSAGE_COUNT, PHONE_CALL_ACTION_WAIT_TIMEOUT

logger = logging.getLogger(__name__)


def process_gather_data(call_sid: str, digit: str) -> VoiceResponse:
    """
    The function processes pressed digit at call time

    Args:
        call_sid (str):
        digit (str): user pressed digit

    Returns:
        response (VoiceResponse)
    """

    response = VoiceResponse()

    success_messages = {
        "1": "Acknowledged",
        "2": "Resolved",
        "3": "Silenced",
    }
    if digit in ["1", "2", "3"]:
        # Success case
        msg = success_messages.get(digit, f"You have pressed digit {digit}")
        response.say(msg)
        process_digit(call_sid, digit)
    else:
        if digit == "4" and PHONE_CALL_ALLOWED_REPEAT_MESSAGE_COUNT > 0:
            # Repeat current alert group message
            message = get_repeat_message(call_sid)
            gather = Gather(
                action=get_gather_url(), method="POST",
                num_digits=1, timeout=PHONE_CALL_ACTION_WAIT_TIMEOUT
            )
            if message:
                gather.say(message)
                gather.pause(length=1)
            gather.say(get_alert_group_gather_instructions())
            response.append(gather)
        # Error wrong digit pressing
        gather = Gather(
            action=get_gather_url(), method="POST",
            num_digits=1, timeout=PHONE_CALL_ACTION_WAIT_TIMEOUT)

        response.say("Wrong digit")
        gather.say(get_alert_group_gather_instructions())

        response.append(gather)

    return response


def get_repeat_message(call_sid: str) -> str | None:
    if not call_sid:
        return None

    twilio_phone_call = (
        TwilioPhoneCall.objects.select_related("phone_call_record__represents_alert_group").filter(sid=call_sid).first()
    )
    if twilio_phone_call is None:
        logger.info(f"twilioapp.get_repeat_message: twilio_phone_call not found sid={call_sid}")
        return None

    phone_call_record = twilio_phone_call.phone_call_record
    if phone_call_record is None:
        logger.info(f"twilioapp.get_repeat_message: twilio_phone_call has no phone_call_record sid={call_sid}")
        return None

    alert_group = phone_call_record.represents_alert_group
    if alert_group is None:
        logger.info(f"twilioapp.get_repeat_message: phone_call_record has no alert_group sid={call_sid}")
        return None

    return AlertGroupPhoneCallRenderer(alert_group).render()


def process_digit(call_sid, digit):
    """
    The function get Phone Call instance according to call_sid
            and run process of pressed digit

            Args:
                call_sid (str):
                digit (str):

            Returns:

    """
    if call_sid and digit:
        logger.info(f"twilioapp.process_digit: processing sid={call_sid} digit={digit}")
        twilio_phone_call = TwilioPhoneCall.objects.filter(sid=call_sid).first()
        if twilio_phone_call is None:
            logger.info(f"twilioapp.process_digit: twilio_phone_call not found sid={call_sid}")
            return

        logger.info(f"twilioapp.process_digit: found twilio_phone_call sid={call_sid} digit={digit}")
        phone_call_record = twilio_phone_call.phone_call_record

        if phone_call_record is None:
            logger.info(f"twilioapp.process_digit: twilio_phone_call has no phone_call_record sid={call_sid}")
            return

        logger.info(f"twilioapp.process_digit: found phone_call_record id={phone_call_record.id} sid={call_sid}")
        alert_group = phone_call_record.represents_alert_group
        user = phone_call_record.receiver
        logger.info(
            f"twilioapp.process_digit: processing digit phone_call_record id={phone_call_record.id} "
            f"twilio_phone_call_sid={call_sid} digit={digit} alert_group_id={alert_group.id} user_id={user.id}"
        )
        if digit == "1":
            alert_group.acknowledge_by_user_or_backsync(user, action_source=ActionSource.PHONE)
        elif digit == "2":
            alert_group.resolve_by_user_or_backsync(user, action_source=ActionSource.PHONE)
        elif digit == "3":
            alert_group.silence_by_user_or_backsync(user, silence_delay=1800, action_source=ActionSource.PHONE)


def get_gather_url():
    return create_engine_url(reverse("twilioapp:gather"))


def get_alert_group_gather_instructions():
    if PHONE_CALL_ALLOWED_REPEAT_MESSAGE_COUNT > 0:
        return "Press 1 to acknowledge, 2 to resolve, 3 to silence for 30 minutes and 4 to repeat this message"
    else:
        return "Press 1 to acknowledge, 2 to resolve, 3 to silence for 30 minutes"
