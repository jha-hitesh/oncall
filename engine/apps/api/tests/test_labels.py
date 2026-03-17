import pytest
from django.conf import settings as django_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.api.permissions import LegacyAccessControlRole
from apps.labels.models import LabelKeyCache, LabelValueCache


@pytest.mark.django_db
def test_labels_get_keys(make_organization_and_user_with_plugin_token, make_user_auth_headers):
    organization, user, token = make_organization_and_user_with_plugin_token()
    key = LabelKeyCache.create_key(organization, "team", prescribed=True)
    LabelValueCache.create_value(key, "platform")

    client = APIClient()
    url = reverse("api-internal:get_keys")
    response = client.get(url, format="json", **make_user_auth_headers(user, token))

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {
            "id": key.id,
            "name": "team",
            "prescribed": True,
            "is_managed_label": False,
            "color_code": django_settings.FEATURE_LABELS_KEY_DEFAULT_COLOR,
            "values_count": 1,
        }
    ]


@pytest.mark.django_db
def test_get_update_key_get(make_organization_and_user_with_plugin_token, make_user_auth_headers):
    organization, user, token = make_organization_and_user_with_plugin_token()
    key = LabelKeyCache.create_key(organization, "team")
    value = LabelValueCache.create_value(key, "platform")

    client = APIClient()
    url = reverse("api-internal:get_update_key", kwargs={"key_id": key.id})
    response = client.get(url, format="json", **make_user_auth_headers(user, token))

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "key": {
            "id": key.id,
            "name": "team",
            "prescribed": False,
            "is_managed_label": False,
            "color_code": django_settings.FEATURE_LABELS_KEY_DEFAULT_COLOR,
            "values_count": 1,
        },
        "values": [
            {"id": value.id, "name": "platform", "prescribed": False, "color_code": django_settings.FEATURE_LABELS_VALUE_DEFAULT_COLOR}
        ],
    }


@pytest.mark.django_db
def test_get_update_key_put(make_organization_and_user_with_plugin_token, make_user_auth_headers):
    organization, user, token = make_organization_and_user_with_plugin_token()
    key = LabelKeyCache.create_key(organization, "team")

    client = APIClient()
    url = reverse("api-internal:get_update_key", kwargs={"key_id": key.id})
    response = client.put(
        url,
        format="json",
        data={"name": "service", "is_managed_label": True, "color_code": "#123456"},
        **make_user_auth_headers(user, token),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["key"]["name"] == "service"
    assert response.json()["key"]["is_managed_label"] is True
    assert response.json()["key"]["color_code"] == "#123456"


@pytest.mark.django_db
def test_get_key_by_name(make_organization_and_user_with_plugin_token, make_user_auth_headers):
    organization, user, token = make_organization_and_user_with_plugin_token()
    key = LabelKeyCache.create_key(organization, "team")
    value = LabelValueCache.create_value(key, "platform")

    client = APIClient()
    url = reverse("api-internal:get_key_by_name", kwargs={"key_name": "team"})
    response = client.get(url, format="json", **make_user_auth_headers(user, token))

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "key": {
            "id": key.id,
            "name": "team",
            "prescribed": False,
            "is_managed_label": False,
            "color_code": django_settings.FEATURE_LABELS_KEY_DEFAULT_COLOR,
            "values_count": 1,
        },
        "values": [
            {"id": value.id, "name": "platform", "prescribed": False, "color_code": django_settings.FEATURE_LABELS_VALUE_DEFAULT_COLOR}
        ],
    }


@pytest.mark.django_db
def test_add_value(make_organization_and_user_with_plugin_token, make_user_auth_headers):
    organization, user, token = make_organization_and_user_with_plugin_token()
    key = LabelKeyCache.create_key(organization, "team")

    client = APIClient()
    url = reverse("api-internal:add_value", kwargs={"key_id": key.id})
    response = client.post(
        url,
        format="json",
        data={"name": "platform", "color_code": "#abcdef"},
        **make_user_auth_headers(user, token),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["values"][0]["name"] == "platform"
    assert response.json()["values"][0]["color_code"] == "#abcdef"


@pytest.mark.django_db
def test_rename_value(make_organization_and_user_with_plugin_token, make_user_auth_headers):
    organization, user, token = make_organization_and_user_with_plugin_token()
    key = LabelKeyCache.create_key(organization, "team")
    value = LabelValueCache.create_value(key, "platform")

    client = APIClient()
    url = reverse("api-internal:get_update_value", kwargs={"key_id": key.id, "value_id": value.id})
    response = client.put(
        url,
        format="json",
        data={"name": "payments", "color_code": "#fedcba"},
        **make_user_auth_headers(user, token),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["values"][0]["name"] == "payments"
    assert response.json()["values"][0]["color_code"] == "#fedcba"


@pytest.mark.django_db
def test_get_value(make_organization_and_user_with_plugin_token, make_user_auth_headers):
    organization, user, token = make_organization_and_user_with_plugin_token()
    key = LabelKeyCache.create_key(organization, "team")
    value = LabelValueCache.create_value(key, "platform")

    client = APIClient()
    url = reverse("api-internal:get_update_value", kwargs={"key_id": key.id, "value_id": value.id})
    response = client.get(url, format="json", **make_user_auth_headers(user, token))

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "id": value.id,
        "name": "platform",
        "prescribed": False,
        "color_code": django_settings.FEATURE_LABELS_VALUE_DEFAULT_COLOR,
    }


@pytest.mark.django_db
def test_labels_create_label(make_organization_and_user_with_plugin_token, make_user_auth_headers):
    _, user, token = make_organization_and_user_with_plugin_token()

    client = APIClient()
    url = reverse("api-internal:create_label")
    response = client.post(
        url,
        format="json",
        data={
            "key": {"name": "team", "is_managed_label": True, "color_code": "#112233"},
            "values": [{"name": "platform", "color_code": "#445566"}],
        },
        **make_user_auth_headers(user, token),
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["key"]["name"] == "team"
    assert response.json()["key"]["is_managed_label"] is True
    assert response.json()["key"]["color_code"] == "#112233"
    assert response.json()["values"][0]["name"] == "platform"
    assert response.json()["values"][0]["color_code"] == "#445566"


@pytest.mark.django_db
def test_labels_feature_false(make_organization_and_user_with_plugin_token, make_user_auth_headers, settings):
    settings.FEATURE_LABELS_ENABLED_FOR_ALL = False

    _, user, token = make_organization_and_user_with_plugin_token()
    client = APIClient()

    response = client.get(reverse("api-internal:get_keys"), format="json", **make_user_auth_headers(user, token))
    assert response.status_code == status.HTTP_404_NOT_FOUND

    response = client.post(
        reverse("api-internal:create_label"),
        format="json",
        data={"key": {"name": "team"}, "values": []},
        **make_user_auth_headers(user, token),
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role,expected_status",
    [
        (LegacyAccessControlRole.ADMIN, status.HTTP_200_OK),
        (LegacyAccessControlRole.EDITOR, status.HTTP_200_OK),
        (LegacyAccessControlRole.VIEWER, status.HTTP_200_OK),
        (LegacyAccessControlRole.NONE, status.HTTP_403_FORBIDDEN),
    ],
)
def test_labels_permissions_get_actions(
    make_organization_and_user_with_plugin_token,
    make_user_auth_headers,
    role,
    expected_status,
):
    organization, user, token = make_organization_and_user_with_plugin_token(role)
    key = LabelKeyCache.create_key(organization, "team")
    value = LabelValueCache.create_value(key, "platform")
    client = APIClient()

    response = client.get(reverse("api-internal:get_keys"), format="json", **make_user_auth_headers(user, token))
    assert response.status_code == expected_status

    response = client.get(
        reverse("api-internal:get_update_key", kwargs={"key_id": key.id}),
        format="json",
        **make_user_auth_headers(user, token),
    )
    assert response.status_code == expected_status

    response = client.get(
        reverse("api-internal:get_update_value", kwargs={"key_id": key.id, "value_id": value.id}),
        format="json",
        **make_user_auth_headers(user, token),
    )
    assert response.status_code == expected_status


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role,expected_status",
    [
        (LegacyAccessControlRole.ADMIN, status.HTTP_200_OK),
        (LegacyAccessControlRole.EDITOR, status.HTTP_403_FORBIDDEN),
        (LegacyAccessControlRole.VIEWER, status.HTTP_403_FORBIDDEN),
        (LegacyAccessControlRole.NONE, status.HTTP_403_FORBIDDEN),
    ],
)
def test_labels_permissions_create_update_actions(
    make_organization_and_user_with_plugin_token,
    make_user_auth_headers,
    role,
    expected_status,
):
    organization, user, token = make_organization_and_user_with_plugin_token(role)
    key = LabelKeyCache.create_key(organization, "team")
    value = LabelValueCache.create_value(key, "platform")
    client = APIClient()

    response = client.put(
        reverse("api-internal:get_update_key", kwargs={"key_id": key.id}),
        format="json",
        data={"name": "service"},
        **make_user_auth_headers(user, token),
    )
    assert response.status_code == expected_status

    response = client.post(
        reverse("api-internal:add_value", kwargs={"key_id": key.id}),
        format="json",
        data={"name": "payments"},
        **make_user_auth_headers(user, token),
    )
    assert response.status_code == expected_status

    response = client.put(
        reverse("api-internal:get_update_value", kwargs={"key_id": key.id, "value_id": value.id}),
        format="json",
        data={"name": "infra"},
        **make_user_auth_headers(user, token),
    )
    assert response.status_code == expected_status

    response = client.post(
        reverse("api-internal:create_label"),
        format="json",
        data={"key": {"name": "another-service"}, "values": []},
        **make_user_auth_headers(user, token),
    )
    expected_create_status = status.HTTP_201_CREATED if expected_status == status.HTTP_200_OK else expected_status
    assert response.status_code == expected_create_status


@pytest.mark.django_db
def test_alert_group_labels_get_keys(
    make_organization_and_user_with_plugin_token,
    make_alert_receive_channel,
    make_alert_group,
    make_alert_group_label_association,
    make_label_key,
    make_user_auth_headers,
):
    organization, user, token = make_organization_and_user_with_plugin_token()

    alert_receive_channel = make_alert_receive_channel(user.organization)
    alert_group = make_alert_group(alert_receive_channel)
    make_label_key(organization, key_name="a", color_code="#112233")
    make_alert_group_label_association(organization, alert_group, key_name="a", value_name="b")

    client = APIClient()
    url = reverse("api-internal:alert_group_labels-get_keys")
    response = client.get(url, format="json", **make_user_auth_headers(user, token))

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [{"id": "a", "name": "a", "color_code": "#112233"}]


@pytest.mark.django_db
def test_alert_group_labels_get_key(
    make_organization_and_user_with_plugin_token,
    make_alert_receive_channel,
    make_alert_group,
    make_alert_group_label_association,
    make_label_key_and_value,
    make_user_auth_headers,
):
    organization, user, token = make_organization_and_user_with_plugin_token()

    alert_receive_channel = make_alert_receive_channel(user.organization)
    alert_group = make_alert_group(alert_receive_channel)
    make_label_key_and_value(organization, key_name="a", value_name="b")
    make_alert_group_label_association(organization, alert_group, key_name="a", value_name="b")

    client = APIClient()
    url = reverse("api-internal:alert_group_labels-get_key", kwargs={"key_id": "a"})
    response = client.get(url, format="json", **make_user_auth_headers(user, token))

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "key": {"id": "a", "name": "a", "color_code": django_settings.FEATURE_LABELS_KEY_DEFAULT_COLOR},
        "values": [{"id": "b", "name": "b", "color_code": django_settings.FEATURE_LABELS_VALUE_DEFAULT_COLOR}],
    }
