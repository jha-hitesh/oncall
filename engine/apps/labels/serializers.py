from rest_framework import serializers

from apps.labels.models import get_default_label_key_color_code, get_default_label_value_color_code


def hex_color_field(default):
    return serializers.RegexField(r"^#[0-9A-Fa-f]{6}$", default=default)


class LabelKeySerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    prescribed = serializers.BooleanField(default=False)
    is_managed_label = serializers.BooleanField(default=False)
    color_code = hex_color_field(get_default_label_key_color_code)
    values_count = serializers.IntegerField(required=False)


class LabelValueSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    prescribed = serializers.BooleanField(default=False)
    color_code = hex_color_field(get_default_label_value_color_code)


class LabelOptionSerializer(serializers.Serializer):
    key = LabelKeySerializer()
    values = LabelValueSerializer(many=True)


class LabelNameSerializer(serializers.Serializer):
    name = serializers.CharField(trim_whitespace=True, allow_blank=False, max_length=200)


class CreateLabelKeySerializer(serializers.Serializer):
    name = serializers.CharField(trim_whitespace=True, allow_blank=False, max_length=200)
    is_managed_label = serializers.BooleanField(default=False)
    color_code = hex_color_field(get_default_label_key_color_code)


class UpdateLabelKeySerializer(serializers.Serializer):
    name = serializers.CharField(trim_whitespace=True, allow_blank=False, max_length=200)
    is_managed_label = serializers.BooleanField(default=False)
    color_code = hex_color_field(get_default_label_key_color_code)


class CreateLabelValueSerializer(serializers.Serializer):
    name = serializers.CharField(trim_whitespace=True, allow_blank=False, max_length=200)
    color_code = hex_color_field(get_default_label_value_color_code)


class CreateLabelSerializer(serializers.Serializer):
    key = CreateLabelKeySerializer()
    values = CreateLabelValueSerializer(many=True)
