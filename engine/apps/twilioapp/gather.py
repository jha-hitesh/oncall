import logging
import json

from django.urls import reverse
from twilio.twiml.voice_response import Gather, VoiceResponse

from apps.alerts.constants import ActionSource
from apps.alerts.incident_appearance.renderers.phone_call_renderer import (
    AlertGroupPhoneCallBundleRenderer,
    AlertGroupPhoneCallRenderer,
)
from apps.alerts.models import BundledNotification
from apps.base.utils import live_settings
from apps.twilioapp.models import TwilioPhoneCall
from common.api_helpers.utils import create_engine_url
from settings.base import PHONE_CALL_ACTION_RESPONSE_TEMPLATE, PHONE_CALL_INSTRUCTIONS_CONFIG, PHONE_CALL_INSTRUCTIONS_TEMPLATE

logger = logging.getLogger(__name__)
DEFAULT_SILENCE_DELAY_SECONDS = 1800
DEFAULT_WAIT_TIME_FOR_USER_ACTION = 5
DEFAULT_ACTION_SUCCESS_MESSAGES = {
    "acknowledge": PHONE_CALL_ACTION_RESPONSE_TEMPLATE.get("acknowledge_success_message", "The alert is Acknowledged"),
    "resolve": PHONE_CALL_ACTION_RESPONSE_TEMPLATE.get("resolve_success_message", "The alert is marked Resolved"),
    "silence": PHONE_CALL_ACTION_RESPONSE_TEMPLATE.get("silence_success_message", "The alert is Silenced"),
}
ACKNOWLEDGE_SKIPPED_RESOLVED_MESSAGE = PHONE_CALL_ACTION_RESPONSE_TEMPLATE.get(
    "acknowledge_skipped_resolved_message",
    "This alert group couldn't be acknowledged because it was marked resolved recently",
)
ACKNOWLEDGE_BUNDLE_SKIPPED_RESOLVED_MESSAGE = PHONE_CALL_ACTION_RESPONSE_TEMPLATE.get(
    "acknowledge_bundle_skipped_resolved_message",
    "Some alert groups couldn't be acknowledged because they were marked resolved recently",
)
ACKNOWLEDGE_BUNDLE_ALL_RESOLVED_MESSAGE = PHONE_CALL_ACTION_RESPONSE_TEMPLATE.get(
    "acknowledge_bundle_all_resolved_message",
    "These alert groups couldn't be acknowledged because they were marked resolved recently",
)
ACTION_SUCCESS_MESSAGE_CONFIG_KEYS = {
    "acknowledge": "acknowledge_message",
    "resolve": "resolve_message",
    "silence": "silence_message",
}
DEFAULT_PHONE_CALL_INSTRUCTIONS_CONFIG = {
    "acknowledge_button": "1",
    "resolve_button": "2",
    "silence_button": "3",
    "wait_time_for_user_action": DEFAULT_WAIT_TIME_FOR_USER_ACTION,
}


def _get_phone_call_instructions_config() -> dict:
    config = live_settings.PHONE_CALL_INSTRUCTIONS_CONFIG
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except json.JSONDecodeError:
            config = None

    if not isinstance(config, dict):
        return PHONE_CALL_INSTRUCTIONS_CONFIG.copy()

    normalized_config = PHONE_CALL_INSTRUCTIONS_CONFIG.copy()
    normalized_config.update(config)
    return normalized_config


def _get_valid_integer_value(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _get_valid_phone_call_button(value) -> str | None:
    if isinstance(value, int):
        value = str(value)
    if isinstance(value, str) and (value.isdigit() or value in {"*", "#"}):
        return value
    return None


def _get_button_digit(config: dict, key: str, *, required: bool = False) -> str | None:
    value = _get_valid_phone_call_button(config.get(key))
    if value is None:
        if required:
            return _get_valid_phone_call_button(DEFAULT_PHONE_CALL_INSTRUCTIONS_CONFIG.get(key))
        return None
    return value


def _get_enabled_actions() -> dict[str, str]:
    config = _get_phone_call_instructions_config()
    actions = {}
    acknowledge_button = _get_button_digit(config, "acknowledge_button", required=True)
    if acknowledge_button is not None:
        actions["acknowledge"] = acknowledge_button

    for action, key in (
        ("resolve", "resolve_button"),
        ("silence", "silence_button"),
        ("repeat", "repeat_button"),
    ):
        button = _get_button_digit(config, key)
        if button is not None:
            actions[action] = button

    return actions


def get_phone_call_wait_time_for_user_action() -> int:
    config = _get_phone_call_instructions_config()
    wait_time = _get_valid_integer_value(config.get("wait_time_for_user_action"))
    return wait_time if wait_time is not None else DEFAULT_WAIT_TIME_FOR_USER_ACTION


def get_phone_call_silence_in_minutes() -> int:
    config = _get_phone_call_instructions_config()
    silence_in_minutes = _get_valid_integer_value(config.get("silence_in_minutes"))
    if silence_in_minutes is None:
        return DEFAULT_SILENCE_DELAY_SECONDS // 60
    return silence_in_minutes


def _get_default_phone_call_instructions_template(enabled_actions: dict[str, str]) -> str:
    action_phrases = []
    if enabled_actions.get("acknowledge") is not None:
        action_phrases.append("Press {acknowledge_button} to acknowledge")
    if enabled_actions.get("resolve") is not None:
        action_phrases.append("{resolve_button} to resolve")
    if enabled_actions.get("silence") is not None:
        action_phrases.append("{silence_button} to silence for {silence_in_minutes} minutes")
    if enabled_actions.get("repeat") is not None:
        action_phrases.append("{repeat_button} to repeat this message")

    if not action_phrases:
        return "No phone call actions are configured"
    if len(action_phrases) == 1:
        return action_phrases[0]
    if len(action_phrases) == 2:
        return " and ".join(action_phrases)
    return ", ".join(action_phrases[:-1]) + f" and {action_phrases[-1]}"


def _get_action_by_digit() -> dict[str, str]:
    return {digit: action for action, digit in _get_enabled_actions().items()}


def _get_action_success_message(action: str) -> str | None:
    config = _get_phone_call_instructions_config()
    config_key = ACTION_SUCCESS_MESSAGE_CONFIG_KEYS.get(action)
    configured_message = config.get(config_key) if config_key else None
    if isinstance(configured_message, str) and configured_message:
        return configured_message
    return DEFAULT_ACTION_SUCCESS_MESSAGES.get(action)


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
    action_by_digit = _get_action_by_digit()
    action = action_by_digit.get(digit)

    success_message = _get_action_success_message(action)
    if success_message is not None:
        if action == "acknowledge":
            result = process_digit(call_sid, action)
            if result is not None and result.get("acknowledged_count", 0) == 0 and result.get("skipped_resolved", 0) > 0:
                if result.get("is_bundle"):
                    response.say(ACKNOWLEDGE_BUNDLE_ALL_RESOLVED_MESSAGE)
                else:
                    response.say(ACKNOWLEDGE_SKIPPED_RESOLVED_MESSAGE)
            elif result is not None and result.get("acknowledged_count", 0) > 0 and result.get("skipped_resolved", 0) > 0:
                response.say(f"{success_message}. {ACKNOWLEDGE_BUNDLE_SKIPPED_RESOLVED_MESSAGE}")
            else:
                response.say(success_message)
        else:
            # Success case
            response.say(success_message)
            process_digit(call_sid, action)
    else:
        if action == "repeat":
            # Repeat current alert group message
            message = get_repeat_message(call_sid)
            gather = Gather(
                action=get_gather_url(), method="POST",
                num_digits=1, timeout=get_phone_call_wait_time_for_user_action()
            )
            if message:
                gather.say(message)
                gather.pause(length=1)
            gather.say(get_alert_group_gather_instructions())
            response.append(gather)
        # Error wrong digit pressing
        gather = Gather(
            action=get_gather_url(), method="POST",
            num_digits=1, timeout=get_phone_call_wait_time_for_user_action())

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

    if phone_call_record.represents_bundle_uuid:
        notifications = BundledNotification.objects.filter(bundle_uuid=phone_call_record.represents_bundle_uuid)
        if not notifications.exists():
            logger.info(
                f"twilioapp.get_repeat_message: phone_call_record bundle has no notifications sid={call_sid}"
            )
            return None
        return AlertGroupPhoneCallBundleRenderer(notifications).render()

    alert_group = phone_call_record.represents_alert_group
    if alert_group is None:
        logger.info(f"twilioapp.get_repeat_message: phone_call_record has no alert_group sid={call_sid}")
        return None

    return AlertGroupPhoneCallRenderer(alert_group).render()


def process_digit(call_sid, action):
    """
    The function get Phone Call instance according to call_sid
            and run process of pressed digit

            Args:
                call_sid (str):
                action (str):

            Returns:

    """
    if call_sid and action:
        logger.info(f"twilioapp.process_digit: processing sid={call_sid} action={action}")
        twilio_phone_call = TwilioPhoneCall.objects.filter(sid=call_sid).first()
        if twilio_phone_call is None:
            logger.info(f"twilioapp.process_digit: twilio_phone_call not found sid={call_sid}")
            return None

        logger.info(f"twilioapp.process_digit: found twilio_phone_call sid={call_sid} action={action}")
        phone_call_record = twilio_phone_call.phone_call_record

        if phone_call_record is None:
            logger.info(f"twilioapp.process_digit: twilio_phone_call has no phone_call_record sid={call_sid}")
            return None

        logger.info(f"twilioapp.process_digit: found phone_call_record id={phone_call_record.id} sid={call_sid}")
        user = phone_call_record.receiver
        if phone_call_record.represents_bundle_uuid:
            notifications = BundledNotification.objects.filter(
                bundle_uuid=phone_call_record.represents_bundle_uuid
            ).select_related("alert_group")
            alert_groups = []
            for notification in notifications:
                if notification.alert_group not in alert_groups:
                    alert_groups.append(notification.alert_group)
            logger.info(
                f"twilioapp.process_digit: processing bundled action phone_call_record id={phone_call_record.id} "
                f"twilio_phone_call_sid={call_sid} action={action} bundle_uuid={phone_call_record.represents_bundle_uuid} "
                f"user_id={user.id} alert_group_count={len(alert_groups)}"
            )
            acknowledged_count = 0
            skipped_resolved = 0
            for alert_group in alert_groups:
                if action == "acknowledge":
                    if alert_group.resolved:
                        skipped_resolved += 1
                        continue
                    alert_group.acknowledge_by_user_or_backsync(user, action_source=ActionSource.PHONE)
                    acknowledged_count += 1
                elif action == "resolve":
                    alert_group.resolve_by_user_or_backsync(user, action_source=ActionSource.PHONE)
                elif action == "silence":
                    alert_group.silence_by_user_or_backsync(
                        user, silence_delay=get_phone_call_silence_in_minutes() * 60, action_source=ActionSource.PHONE
                    )
            if action == "acknowledge":
                return {
                    "is_bundle": True,
                    "acknowledged_count": acknowledged_count,
                    "skipped_resolved": skipped_resolved,
                    "total": len(alert_groups),
                }
        else:
            alert_group = phone_call_record.represents_alert_group
            logger.info(
                f"twilioapp.process_digit: processing action phone_call_record id={phone_call_record.id} "
                f"twilio_phone_call_sid={call_sid} action={action} alert_group_id={alert_group.id} user_id={user.id}"
            )
            if action == "acknowledge":
                if alert_group.resolved:
                    return {"is_bundle": False, "acknowledged_count": 0, "skipped_resolved": 1, "total": 1}
                alert_group.acknowledge_by_user_or_backsync(user, action_source=ActionSource.PHONE)
                return {"is_bundle": False, "acknowledged_count": 1, "skipped_resolved": 0, "total": 1}
            elif action == "resolve":
                alert_group.resolve_by_user_or_backsync(user, action_source=ActionSource.PHONE)
            elif action == "silence":
                alert_group.silence_by_user_or_backsync(
                    user, silence_delay=get_phone_call_silence_in_minutes() * 60, action_source=ActionSource.PHONE
                )
    return None


def get_gather_url():
    return create_engine_url(reverse("twilioapp:gather"))


def get_alert_group_gather_instructions():
    enabled_actions = _get_enabled_actions()
    template = live_settings.PHONE_CALL_INSTRUCTIONS_TEMPLATE
    if not template:
        template = _get_default_phone_call_instructions_template(enabled_actions)
    return template.format(
        acknowledge_button=enabled_actions.get("acknowledge", ""),
        resolve_button=enabled_actions.get("resolve", ""),
        silence_button=enabled_actions.get("silence", ""),
        repeat_button=enabled_actions.get("repeat", ""),
        silence_in_minutes=get_phone_call_silence_in_minutes(),
    )
