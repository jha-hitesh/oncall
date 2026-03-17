from rest_framework import serializers

from apps.labels.models import (
    AssociatedLabel,
    LabelKeyCache,
    LabelValueCache,
    get_default_label_key_color_code,
    get_default_label_value_color_code,
)
from apps.labels.utils import is_labels_feature_enabled


class LabelKeySerializer(serializers.ModelSerializer):
    id = serializers.CharField()
    prescribed = serializers.BooleanField(default=False)
    is_managed_label = serializers.BooleanField(default=False)
    color_code = serializers.RegexField(r"^#[0-9A-Fa-f]{6}$", default=get_default_label_key_color_code)

    class Meta:
        model = LabelKeyCache
        fields = (
            "id",
            "name",
            "prescribed",
            "is_managed_label",
            "color_code",
        )


class LabelValueSerializer(serializers.ModelSerializer):
    id = serializers.CharField()
    prescribed = serializers.BooleanField(default=False)
    color_code = serializers.RegexField(r"^#[0-9A-Fa-f]{6}$", default=get_default_label_value_color_code)

    class Meta:
        model = LabelValueCache
        fields = (
            "id",
            "name",
            "prescribed",
            "color_code",
        )


class LabelPairSerializer(serializers.Serializer):
    key = LabelKeySerializer()
    value = LabelValueSerializer()


class LabelOptionSerializer(serializers.Serializer):
    key = LabelKeySerializer()
    values = LabelValueSerializer(many=True)


class LabelReprSerializer(serializers.Serializer):
    name = serializers.CharField()


class LabelsSerializerMixin(serializers.Serializer):
    labels = LabelPairSerializer(many=True, required=False)

    def validate_labels(self, labels):
        if labels:
            keys = {label["key"]["id"] for label in labels}
            if len(keys) != len(labels):
                raise serializers.ValidationError(detail="Duplicate label key")
        return labels

    def update_labels_association_if_needed(self, labels, instance, organization):
        if labels is not None and is_labels_feature_enabled(organization):
            AssociatedLabel.update_association(labels, instance, organization)
