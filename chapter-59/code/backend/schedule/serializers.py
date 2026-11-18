from rest_framework import serializers

from core.api_fields import LocalDateTimeField
from core.timeutils import TimeInputError, get_zone, parse_local_date

from .recurrence import RuleError, parse_rule


class EventSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")
    location = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    start = LocalDateTimeField(source="start_at")
    end = LocalDateTimeField(source="end_at")
    recurrence = serializers.JSONField(required=False, allow_null=True, default=None)
    remind_minutes_before = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=1440, default=None)

    def validate_recurrence(self, value):
        if value is not None:
            try:
                parse_rule(value)
            except RuleError as exc:
                raise serializers.ValidationError(str(exc)) from exc
        return value


class RangeSerializer(serializers.Serializer):
    start = serializers.CharField()
    end = serializers.CharField()

    def validate(self, attrs):
        try:
            attrs["start_day"], attrs["end_day"] = parse_local_date(attrs["start"]), parse_local_date(attrs["end"])
        except TimeInputError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return attrs


class PreferencesSerializer(serializers.Serializer):
    timezone = serializers.CharField(max_length=64)
    work_start = serializers.TimeField(required=False)
    work_end = serializers.TimeField(required=False)
    work_days = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=6), required=False, max_length=7)
    briefing_enabled = serializers.BooleanField(required=False)
    briefing_time = serializers.TimeField(required=False)

    def validate_timezone(self, value):
        try:
            get_zone(value)
        except TimeInputError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value
