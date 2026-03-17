import json
import logging
import typing

from apps.labels import types
from apps.labels.utils import is_labels_feature_enabled
from common.jinja_templater import apply_jinja_template
from common.jinja_templater.apply_jinja_template import JinjaTemplateError, JinjaTemplateWarning

if typing.TYPE_CHECKING:
    from apps.alerts.models import Alert, AlertGroup, AlertReceiveChannel

logger = logging.getLogger(__name__)

# What can be used as a label key/value coming out from the template
LABEL_VALUE_TYPES = (str, int, float, bool)

# Maximum number of labels per alert group, excess labels will be dropped
MAX_LABELS_PER_ALERT_GROUP = 15


def gather_alert_labels(
    alert_receive_channel: "AlertReceiveChannel", raw_request_data: "Alert.RawRequestData"
) -> typing.Optional[types.AlertLabels]:
    """
    gather_alert_labels gathers labels for an alert received by the alert receive channel.
    1. static labels - inherits them from integration.
    2. dynamic labels and multi-label extraction template – templating the raw_request_data.
    """
    if not is_labels_feature_enabled(alert_receive_channel.organization):
        return None

    # apply static labels by inheriting labels from the integration
    labels = {
        label.key.name: label.value.name for label in alert_receive_channel.labels.all().select_related("key", "value")
    }

    labels.update(_apply_dynamic_labels(alert_receive_channel, raw_request_data))

    labels.update(_apply_multi_label_extraction_template(alert_receive_channel, raw_request_data))

    return labels


def save_alert_group_labels(
    alert_group: "AlertGroup", alert_receive_channel: "AlertReceiveChannel", labels: typing.Optional[types.AlertLabels]
) -> None:
    from apps.labels.models import AlertGroupAssociatedLabel

    if not is_labels_feature_enabled(alert_receive_channel.organization) or not labels:
        return

    # create associated labels
    alert_group_labels = [
        AlertGroupAssociatedLabel(
            alert_group=alert_group,
            organization=alert_receive_channel.organization,
            key_name=key,
            value_name=value,
        )
        for key, value in labels.items()
    ]
    # sort associated labels by key and value
    alert_group_labels.sort(key=lambda label: (label.key_name, label.value_name))

    # only keep up to MAX_LABELS_PER_ALERT_GROUP labels per alert group
    if len(alert_group_labels) > MAX_LABELS_PER_ALERT_GROUP:
        logger.warning(
            "Too many labels for alert group %s. Dropping %d labels.",
            alert_group.id,
            len(alert_group_labels) - MAX_LABELS_PER_ALERT_GROUP,
        )
        alert_group_labels = alert_group_labels[:MAX_LABELS_PER_ALERT_GROUP]

    # bulk create associated labels
    AlertGroupAssociatedLabel.objects.bulk_create(alert_group_labels)


def _apply_dynamic_labels(
    alert_receive_channel: "AlertReceiveChannel", raw_request_data: "Alert.RawRequestData"
) -> types.AlertLabels:
    from apps.labels.models import LabelKeyCache, LabelValueCache

    if alert_receive_channel.alert_group_labels_custom is None:
        return {}

    # fetch up-to-date label key names
    label_keys = {
        k.id: {"name": k.name, "is_managed_label": k.is_managed_label}
        for k in LabelKeyCache.objects.filter(
            id__in=[label[0] for label in alert_receive_channel.alert_group_labels_custom]
        ).only("id", "name", "is_managed_label")
    }
    label_value_names = {
        v.id: v.name
        for v in LabelValueCache.objects.filter(
            id__in=[label[1] for label in alert_receive_channel.alert_group_labels_custom if label[1]]
        ).only("id", "name")
    }
    managed_label_values = _get_managed_label_values_by_key_id(
        alert_receive_channel.organization_id,
        [key_id for key_id, key in label_keys.items() if key["is_managed_label"]],
    )

    result_labels = {}
    for label in alert_receive_channel.alert_group_labels_custom:
        label = _apply_dynamic_label_entry(label, label_keys, label_value_names, managed_label_values, raw_request_data)
        if label:
            key, value = label
            result_labels[key] = value

    # Direct paging can provide selected values for configured dynamic labels.
    # Apply those last so they override inherited integration labels and static custom labels.
    result_labels.update(_apply_dynamic_labels_map(alert_receive_channel, raw_request_data, label_keys, managed_label_values))

    return result_labels


def _apply_dynamic_label_entry(
    label: "AlertReceiveChannel.DynamicLabelsEntryDB",
    keys: dict,
    values: dict,
    managed_label_values: dict[str, set[str]],
    payload: "Alert.RawRequestData",
) -> typing.Optional[tuple[str, str]]:
    key_id, value_id, template = label
    key, value = "", ""
    is_managed_label = False

    # check if key exists
    if key_id in keys:
        key = keys[key_id]["name"]
        is_managed_label = keys[key_id]["is_managed_label"]
    else:
        logger.warning("Label key cache not found. %s", key_id)
        return None

    if value_id:
        if value_id in values:
            value = values[value_id]
        else:
            logger.warning("Label value cache not found. %s", value_id)
            return None
    elif template:
        # otherwise, it's a key-template pair, applying template
        try:
            value = apply_jinja_template(template, payload)
        except (JinjaTemplateError, JinjaTemplateWarning) as e:
            logger.warning("Failed to apply template. %s", e.fallback_message)
            return None
        if not _validate_templated_value(value):
            return None
        if is_managed_label and not _managed_label_value_exists(key_id, value, managed_label_values):
            logger.warning("Managed label value does not exist. %s=%s", key, value)
            return None
    else:
        logger.warning("Label value is neither a value_id, nor a template. %s", key)
    return key, value


def _apply_multi_label_extraction_template(
    alert_receive_channel: "AlertReceiveChannel", raw_request_data: "Alert.RawRequestData"
) -> types.AlertLabels:
    from apps.labels.models import LabelKeyCache, MAX_KEY_NAME_LENGTH

    if not alert_receive_channel.alert_group_labels_template:
        return {}

    # render template - output will be a string.
    # It's expected that it will be a JSON string, to be parsed into a dict.
    try:
        rendered_labels = apply_jinja_template(alert_receive_channel.alert_group_labels_template, raw_request_data)
    except (JinjaTemplateError, JinjaTemplateWarning) as e:
        logger.warning("Failed to apply template. %s", e.fallback_message)
        return {}

    # unmarshal rendered_labels JSON string to dict
    try:
        labels_dict = json.loads(rendered_labels)
    except (TypeError, json.JSONDecodeError):
        # it's expected, if user misconfigured the template
        logger.warning("Failed to parse template result. %s", rendered_labels)
        return {}

    if not isinstance(labels_dict, dict):
        logger.warning("Template result is not a dict. %s", labels_dict)
        return {}

    managed_keys_by_name = {
        key.name: key.id
        for key in LabelKeyCache.objects.filter(
            organization=alert_receive_channel.organization,
            is_managed_label=True,
            name__in=labels_dict.keys(),
        ).only("id", "name")
    }
    managed_label_values = _get_managed_label_values_by_key_id(
        alert_receive_channel.organization_id, managed_keys_by_name.values()
    )

    # validate dict of labels, drop invalid keys & values, convert all values to strings
    result_labels = {}
    for key in labels_dict:
        # check key length
        if len(key) == 0:
            logger.warning("Template result key is empty. %s", key)
            continue

        if len(key) > MAX_KEY_NAME_LENGTH:
            logger.warning("Template result key is too long. %s", key)
            continue

        # Checks specific to multi-label extraction template, because we're receiving value from a JSON:
        # 1. check type
        # 2. convert back to string
        if not isinstance(labels_dict[key], LABEL_VALUE_TYPES):
            logger.warning("Templated value has invalid type. %s", labels_dict[key])
            continue
        value = str(labels_dict[key])

        # apply common value checks
        if not _validate_templated_value(value):
            continue
        if key in managed_keys_by_name and not _managed_label_value_exists(
            managed_keys_by_name[key], value, managed_label_values
        ):
            logger.warning("Managed label value does not exist. %s=%s", key, value)
            continue

        result_labels[key] = value

    return result_labels


def _apply_dynamic_labels_map(
    alert_receive_channel: "AlertReceiveChannel",
    raw_request_data: "Alert.RawRequestData",
    label_keys: dict[str, dict[str, typing.Any]],
    managed_label_values: dict[str, set[str]],
) -> types.AlertLabels:
    from apps.labels.models import MAX_KEY_NAME_LENGTH

    dynamic_labels_map = raw_request_data.get("dynamic_labels_map")
    if not isinstance(dynamic_labels_map, dict):
        return {}

    result_labels = {}
    for key_id, value_id, _ in alert_receive_channel.alert_group_labels_custom or []:
        if value_id is not None or key_id not in label_keys:
            continue

        key_name = label_keys[key_id]["name"]
        if len(key_name) == 0 or len(key_name) > MAX_KEY_NAME_LENGTH:
            continue

        if key_name not in dynamic_labels_map:
            continue

        value = dynamic_labels_map[key_name]
        if not isinstance(value, LABEL_VALUE_TYPES):
            logger.warning("dynamic_labels_map value has invalid type. %s", value)
            continue

        value = str(value)
        if not _validate_templated_value(value):
            continue
        if label_keys[key_id]["is_managed_label"] and not _managed_label_value_exists(
            key_id, value, managed_label_values
        ):
            logger.warning("Managed label value does not exist. %s=%s", key_name, value)
            continue

        result_labels[key_name] = value

    return result_labels


def _get_managed_label_values_by_key_id(organization_id: int, key_ids: typing.Iterable[str]) -> dict[str, set[str]]:
    from apps.labels.models import LabelValueCache

    key_ids = list(key_ids)
    if not key_ids:
        return {}

    result: dict[str, set[str]] = {}
    for value in LabelValueCache.objects.filter(key__organization_id=organization_id, key_id__in=key_ids).only(
        "key_id", "name"
    ):
        result.setdefault(value.key_id, set()).add(value.name)
    return result


def _managed_label_value_exists(key_id: str, value: str, managed_label_values: dict[str, set[str]]) -> bool:
    return value in managed_label_values.get(key_id, set())


def _validate_templated_value(value: str) -> bool:
    from apps.labels.models import MAX_VALUE_NAME_LENGTH

    # check value length
    if len(value) == 0:
        logger.warning("Templated value value is empty. %s", value)
        return False

    if len(value) > MAX_VALUE_NAME_LENGTH:
        logger.warning("Templated value is too long. %s", value)
        return False

    if value.lower().strip() == "none":
        logger.warning("Templated value is None. %s", value)
        return False
    return True
