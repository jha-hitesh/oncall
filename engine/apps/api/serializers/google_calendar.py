from rest_framework import serializers


class GoogleCalendarEventCreateSerializer(serializers.Serializer):
    summary = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    attendees = serializers.ListField(child=serializers.EmailField(), required=False, allow_empty=True)

    def validate(self, attrs):
        start = attrs["start"]
        end = attrs["end"]

        if start.tzinfo is None or end.tzinfo is None:
            raise serializers.ValidationError("start and end must include timezone information")

        if end <= start:
            raise serializers.ValidationError("end must be later than start")

        return attrs


class GoogleCalendarEventCreateResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    html_link = serializers.URLField(required=False, allow_null=True)
    hangout_link = serializers.URLField(required=False, allow_null=True)
