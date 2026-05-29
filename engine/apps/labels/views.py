from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.api.permissions import RBACPermission
from apps.auth_token.auth import PluginAuthentication
from apps.labels.models import LabelKeyCache, LabelValueCache
from apps.labels.utils import is_labels_feature_enabled

from .serializers import (
    CreateLabelSerializer,
    CreateLabelValueSerializer,
    LabelKeySerializer,
    LabelOptionSerializer,
    LabelValueSerializer,
    UpdateLabelKeySerializer,
)


class LabelsFeatureFlagViewSet(ViewSet):
    def initial(self, request, *args, **kwargs):
        if not is_labels_feature_enabled(self.request.auth.organization):
            raise NotFound
        super().initial(request, *args, **kwargs)


class LabelsViewSet(LabelsFeatureFlagViewSet):
    authentication_classes = (PluginAuthentication,)
    permission_classes = (IsAuthenticated, RBACPermission)
    rbac_permissions = {
        "create_label": [RBACPermission.Permissions.ADMIN],
        "rename_key": [RBACPermission.Permissions.ADMIN],
        "delete_key": [RBACPermission.Permissions.ADMIN],
        "add_value": [RBACPermission.Permissions.ADMIN],
        "rename_value": [RBACPermission.Permissions.ADMIN],
        "delete_value": [RBACPermission.Permissions.ADMIN],
        "get_keys": [RBACPermission.Permissions.LABEL_READ],
        "get_key": [RBACPermission.Permissions.LABEL_READ],
        "get_key_by_name": [RBACPermission.Permissions.LABEL_READ],
        "get_value": [RBACPermission.Permissions.LABEL_READ],
    }

    @property
    def organization(self):
        return self.request.auth.organization

    def _get_key(self, key_id: str) -> LabelKeyCache:
        try:
            return LabelKeyCache.objects.prefetch_related("values").get(id=key_id, organization=self.organization)
        except LabelKeyCache.DoesNotExist as exc:
            raise exceptions.NotFound(detail="not found") from exc

    def _get_key_by_name(self, key_name: str) -> LabelKeyCache:
        try:
            return LabelKeyCache.objects.prefetch_related("values").get(name=key_name, organization=self.organization)
        except LabelKeyCache.DoesNotExist as exc:
            raise exceptions.NotFound(detail="not found") from exc

    def _get_value(self, key: LabelKeyCache, value_id: str) -> LabelValueCache:
        try:
            return key.values.get(id=value_id)
        except LabelValueCache.DoesNotExist as exc:
            raise exceptions.NotFound(detail="not found") from exc

    def _validate(self, serializer_class, data):
        serializer = serializer_class(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @extend_schema(responses=LabelKeySerializer(many=True))
    def get_keys(self, request):
        keys = LabelKeyCache.with_values_count().filter(organization=self.organization).order_by("name", "id")
        return Response([key.to_representation() for key in keys])

    @extend_schema(responses=LabelOptionSerializer)
    def get_key(self, request, key_id):
        return Response(self._get_key(key_id).to_option_representation())

    @extend_schema(responses=LabelOptionSerializer)
    def get_key_by_name(self, request, key_name):
        return Response(self._get_key_by_name(key_name).to_option_representation())

    @extend_schema(responses=LabelValueSerializer)
    def get_value(self, request, key_id, value_id):
        key = self._get_key(key_id)
        return Response(self._get_value(key, value_id).to_representation())

    @extend_schema(request=CreateLabelSerializer, responses={201: LabelOptionSerializer})
    def create_label(self, request):
        payload = self._validate(CreateLabelSerializer, request.data)
        key_name = payload["key"]["name"]
        is_managed_label = payload["key"]["is_managed_label"]
        key_color_code = payload["key"]["color_code"]

        if LabelKeyCache.objects.filter(organization=self.organization, name=key_name).exists():
            raise exceptions.ValidationError(detail="label key already exists")

        values_data = payload["values"]
        value_names = [value["name"] for value in values_data]
        if len(value_names) != len(set(value_names)):
            raise exceptions.ValidationError(detail="duplicate label values are not allowed")

        key = LabelKeyCache.create_key(
            self.organization,
            key_name,
            is_managed_label=is_managed_label,
            color_code=key_color_code,
        )
        for value_data in values_data:
            LabelValueCache.create_value(key, value_data["name"], color_code=value_data["color_code"])

        key = LabelKeyCache.objects.prefetch_related("values").get(pk=key.pk)
        return Response(key.to_option_representation(), status=status.HTTP_201_CREATED)

    @extend_schema(request=CreateLabelValueSerializer, responses=LabelOptionSerializer)
    def add_value(self, request, key_id):
        key = self._get_key(key_id)
        payload = self._validate(CreateLabelValueSerializer, request.data)
        value_name = payload["name"]

        if key.values.filter(name=value_name).exists():
            raise exceptions.ValidationError(detail="label value already exists")

        LabelValueCache.create_value(key, value_name, color_code=payload["color_code"])
        key = LabelKeyCache.objects.prefetch_related("values").get(pk=key.pk)
        return Response(key.to_option_representation())

    @extend_schema(request=UpdateLabelKeySerializer, responses=LabelOptionSerializer)
    def rename_key(self, request, key_id):
        key = self._get_key(key_id)
        payload = self._validate(UpdateLabelKeySerializer, request.data)
        new_name = payload["name"]
        is_managed_label = payload["is_managed_label"]
        color_code = payload["color_code"]

        if LabelKeyCache.objects.filter(organization=self.organization, name=new_name).exclude(pk=key.pk).exists():
            raise exceptions.ValidationError(detail="label key already exists")

        key.name = new_name
        key.is_managed_label = is_managed_label
        key.color_code = color_code
        key.save(update_fields=["name", "is_managed_label", "color_code", "last_synced"])
        key = LabelKeyCache.objects.prefetch_related("values").get(pk=key.pk)
        return Response(key.to_option_representation())

    def delete_key(self, request, key_id):
        key = self._get_key(key_id)
        key.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=CreateLabelValueSerializer, responses=LabelOptionSerializer)
    def rename_value(self, request, key_id, value_id):
        key = self._get_key(key_id)
        value = self._get_value(key, value_id)
        payload = self._validate(CreateLabelValueSerializer, request.data)
        new_name = payload["name"]

        if key.values.filter(name=new_name).exclude(pk=value.pk).exists():
            raise exceptions.ValidationError(detail="label value already exists")

        value.name = new_name
        value.color_code = payload["color_code"]
        value.save(update_fields=["name", "color_code", "last_synced"])
        key = LabelKeyCache.objects.prefetch_related("values").get(pk=key.pk)
        return Response(key.to_option_representation())

    def delete_value(self, request, key_id, value_id):
        key = self._get_key(key_id)
        value = self._get_value(key, value_id)
        value.delete()
        key = LabelKeyCache.objects.prefetch_related("values").get(pk=key.pk)
        return Response(key.to_option_representation())

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        if response is None:
            return response

        if "detail" in response.data:
            detail = response.data["detail"]
            if isinstance(detail, list):
                detail = detail[0]
            response.data = {"message": str(detail)}
            return response

        if response.status_code >= 400 and isinstance(response.data, dict):
            non_field_errors = response.data.get("non_field_errors")
            if isinstance(non_field_errors, list) and non_field_errors:
                response.data = {"message": str(non_field_errors[0])}

        return response
