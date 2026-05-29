import logging

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import RBACPermission
from apps.api.serializers.labels import LabelKeySerializer, LabelOptionSerializer
from apps.auth_token.auth import PluginAuthentication
from apps.labels.models import (
    LabelKeyCache,
    LabelValueCache,
    get_default_label_key_color_code,
    get_default_label_value_color_code,
)
from apps.labels.tasks import update_instances_labels_cache
from apps.labels.utils import is_labels_feature_enabled
from apps.labels.views import LabelsFeatureFlagViewSet

logger = logging.getLogger(__name__)


# specifying a tag explicitly to avoid these endpoints being grouped with alert group endpoints
@extend_schema(tags=["alert group labels"])
class AlertGroupLabelsViewSet(LabelsFeatureFlagViewSet):
    """
    This viewset is similar to LabelsViewSet, but it works with alert group labels.
    Alert group labels are stored in the database, not in the label repo.
    """

    permission_classes = (IsAuthenticated, RBACPermission)
    authentication_classes = (PluginAuthentication,)
    rbac_permissions = {
        "get_keys": [RBACPermission.Permissions.ALERT_GROUPS_READ],
        "get_key": [RBACPermission.Permissions.ALERT_GROUPS_READ],
    }

    @extend_schema(responses=LabelKeySerializer(many=True))
    def get_keys(self, request):
        """
        List of alert group label keys.
        IDs are the same as names to keep the response format consistent with LabelsViewSet.get_keys().
        """
        organization = self.request.auth.organization
        names = list(organization.alert_group_labels.values_list("key_name", flat=True).distinct())
        key_colors = {
            key.name: key.color_code
            for key in LabelKeyCache.objects.filter(organization=organization, name__in=names).only("name", "color_code")
        }
        return Response(
            [{"id": name, "name": name, "color_code": key_colors.get(name, get_default_label_key_color_code())} for name in names]
        )

    @extend_schema(responses=LabelOptionSerializer)
    def get_key(self, request, key_id):
        """Key with the list of values. IDs and names are interchangeable (see get_keys() for more details)."""
        organization = self.request.auth.organization
        values = list(organization.alert_group_labels.filter(key_name=key_id).values_list("value_name", flat=True).distinct())
        key_color = (
            LabelKeyCache.objects.filter(organization=organization, name=key_id).values_list("color_code", flat=True).first()
            or get_default_label_key_color_code()
        )
        value_colors = {
            value.name: value.color_code
            for value in LabelValueCache.objects.filter(
                key__organization=organization, key__name=key_id, name__in=values
            ).only("name", "color_code")
        }
        return Response(
            {
                "key": {"id": key_id, "name": key_id, "color_code": key_color},
                "values": [
                    {"id": value, "name": value, "color_code": value_colors.get(value, get_default_label_value_color_code())}
                    for value in values
                ],
            }
        )


def schedule_update_label_cache(model_name, org, ids):
    if not is_labels_feature_enabled(org):
        return
    logger.info(f"start update_instances_labels_cache for ids: {ids}")
    update_instances_labels_cache.apply_async((org.id, ids, model_name))
