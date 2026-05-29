DEFAULT_SLACK_CREATE_CUSTOM_CHANNEL_TEMPLATE = "false"
DEFAULT_SLACK_CHANNEL_PAYLOAD_TEMPLATE = """
{
    "name": "{{ payload.get('title') | lower }}-{{ (payload.alerts.0.startsAt|string)[:10] }}",
    "is_private": false
}
"""
DEFAULT_GOOGLE_CALENDAR_TITLE_TEMPLATE = "{{ payload.get('title', 'Incident') }}"
DEFAULT_GOOGLE_CALENDAR_DESCRIPTION_TEMPLATE = """{{ payload.get('message', '') }}"""
