from django.conf import settings

from .common import (
    DEFAULT_GOOGLE_CALENDAR_DESCRIPTION_TEMPLATE,
    DEFAULT_GOOGLE_CALENDAR_TITLE_TEMPLATE,
    DEFAULT_SLACK_CHANNEL_PAYLOAD_TEMPLATE,
    DEFAULT_SLACK_CREATE_CUSTOM_CHANNEL_TEMPLATE,
)

# Main
enabled = True
title = "Inbound Email"
slug = "inbound_email"
short_description = None
description = None
is_displayed_on_web = settings.FEATURE_INBOUND_EMAIL_ENABLED
is_featured = False
is_able_to_autoresolve = True
is_demo_alert_enabled = True


# Default templates
slack_title = """\
*<{{ grafana_oncall_link }}|#{{ grafana_oncall_incident_id }} {{ payload.get("subject", "Title undefined (check Slack Title Template)") }}>* via {{ integration_name }}
{% if source_link %}
 (*<{{ source_link }}|source>*)
{%- endif %}"""

slack_message = "{{ payload.message }}"

slack_image_url = "{{ payload.image_url }}"
slack_create_custom_channel = DEFAULT_SLACK_CREATE_CUSTOM_CHANNEL_TEMPLATE
slack_channel_payload = DEFAULT_SLACK_CHANNEL_PAYLOAD_TEMPLATE
google_calendar_title = DEFAULT_GOOGLE_CALENDAR_TITLE_TEMPLATE
google_calendar_description = DEFAULT_GOOGLE_CALENDAR_DESCRIPTION_TEMPLATE

web_title = '{{ payload.get("subject", "Title undefined (check Web Title Template)") }}'

web_message = slack_message

web_image_url = slack_image_url

sms_title = web_title

phone_call_title = web_title

telegram_title = sms_title

telegram_message = slack_message

telegram_image_url = slack_image_url

source_link = None

grouping_id = '{{ payload.get("subject", "").upper() }}'

resolve_condition = '{{ payload.get("message", "").upper() == "OK" }}'

acknowledge_condition = None

example_payload = {"subject": "Test email subject", "message": "Test email message", "sender": "sender@example.com"}
