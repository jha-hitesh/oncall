from common.utils import (
    parse_phone_call_action_response_template,
    parse_phone_call_instructions_config,
    validate_alert_group_phone_call_template,
    validate_notification_bundle_phonecall_template,
    validate_phone_call_instructions_template,
)


def test_validate_alert_group_phone_call_template_rejects_unknown_variables():
    error = validate_alert_group_phone_call_template("Alert from {invalid_key}")

    assert error == (
        "Invalid template variable: invalid_key. "
        "Allowed variables are: alert_count, integration_name, title"
    )


def test_validate_phone_call_instructions_template_rejects_invalid_format_template():
    error = validate_phone_call_instructions_template("Press {acknowledge_button")

    assert error == "Invalid format template: expected '}' before end of string"


def test_validate_notification_bundle_phonecall_template_rejects_unknown_variables():
    error = validate_notification_bundle_phonecall_template("{{ invalid_key }}")

    assert error == (
        "Invalid template variable: invalid_key. Allowed variables are: "
        "alert_group_codes, alert_group_names, channel_names, stack_slug, total_alert_groups, total_channels"
    )


def test_validate_notification_bundle_phonecall_template_rejects_invalid_jinja():
    error = validate_notification_bundle_phonecall_template("{% if total_alert_groups %}")

    assert "Invalid Jinja template:" in error


def test_parse_phone_call_instructions_config_rejects_invalid_json():
    config, error = parse_phone_call_instructions_config('{"acknowledge_button": }')

    assert config is None
    assert error == "Invalid JSON: Expecting value"


def test_parse_phone_call_instructions_config_rejects_duplicate_buttons():
    config, error = parse_phone_call_instructions_config(
        {
            "acknowledge_button": "1",
            "resolve_button": "1",
        }
    )

    assert config is None
    assert error == "Invalid value for button configuration: 1 is used by acknowledge_button, resolve_button"


def test_parse_phone_call_action_response_template_rejects_invalid_json():
    template, error = parse_phone_call_action_response_template('{"acknowledge_skipped_resolved_message": }')

    assert template is None
    assert error == "Invalid JSON: Expecting value"


def test_parse_phone_call_action_response_template_rejects_unknown_keys():
    template, error = parse_phone_call_action_response_template({"unknown_key": "x"})

    assert template is None
    assert "Invalid key unknown_key:" in error


def test_parse_phone_call_action_response_template_accepts_valid_partial_config():
    template, error = parse_phone_call_action_response_template(
        {"acknowledge_skipped_resolved_message": "Resolved already"}
    )

    assert error is None
    assert template == {"acknowledge_skipped_resolved_message": "Resolved already"}
