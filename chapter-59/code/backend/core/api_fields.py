"""One API convention for time: clients send and receive LOCAL time strings; the server
owns the conversion."""
from datetime import datetime

from rest_framework import serializers

from core.timeutils import TimeInputError, format_local, parse_local_datetime, resolve_local


class LocalDateTimeField(serializers.Field):
    """'2026-11-12T15:00' in the user's own time zone <-> an aware UTC datetime. Needs
    context["tz"]."""

    default_error_messages = {"invalid": "Use local time like 2026-11-12T15:00, without an offset."}

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        try:
            return resolve_local(parse_local_datetime(data), self.context["tz"]).utc
        except TimeInputError:
            self.fail("invalid")

    def to_representation(self, value: datetime):
        return format_local(value, self.context["tz"])


class UserZoneMixin:
    """Adds the signed-in user's time zone to the serializer context."""

    def get_serializer_context(self):
        # late import: avoids a cycle with the schedule app
        from schedule.services import user_zone
        context = super().get_serializer_context()
        context["tz"] = user_zone(self.request.user)
        return context
