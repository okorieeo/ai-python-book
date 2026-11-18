from datetime import timedelta

from django.http import Http404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.throttles import BurstThrottle
from core.timeutils import format_local, local_day_bounds

from . import services
from .models import Event
from .serializers import EventSerializer, PreferencesSerializer, RangeSerializer


def _event_json(event: Event, tz) -> dict:
    return {"id": str(event.public_id), "title": event.title, "description": event.description, "location": event.location,
            "start": format_local(event.start_at, tz), "end": format_local(event.end_at, tz),
            "recurrence": event.recurrence, "remind_minutes_before": event.remind_minutes_before}


class EventListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [BurstThrottle]

    def get(self, request):
        """GET /api/v1/events/?start=2026-11-09&end=2026-11-15  ->  occurrences with
        repeats expanded."""
        params = RangeSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        tz = services.user_zone(request.user)
        start = local_day_bounds(params.validated_data["start_day"], tz)[0]
        end = local_day_bounds(params.validated_data["end_day"], tz)[1]
        try:
            found = services.occurrences_between(user=request.user, start=start, end=end)
        except services.EventValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"results": [
            {"event_id": str(o.event.public_id), "title": o.event.title, "start": format_local(o.start, tz),
             "end": format_local(o.end, tz), "recurring": o.recurring} for o in found]})

    def post(self, request):
        tz = services.user_zone(request.user)
        serializer = EventSerializer(data=request.data, context={"tz": tz})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            event, clashes = services.create_event(
                user=request.user, tz=tz, title=data["title"], description=data["description"], location=data["location"],
                start_local=data["start_at"].astimezone(tz).replace(tzinfo=None),
                end_local=data["end_at"].astimezone(tz).replace(tzinfo=None),
                recurrence=data["recurrence"], remind_minutes_before=data["remind_minutes_before"])
        except services.EventValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({**_event_json(event, tz), "overlaps": len(clashes)}, status=status.HTTP_201_CREATED)


class EventDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [BurstThrottle]

    def _get(self, request, public_id) -> Event:
        try:
            return services.get_event_for_user(user=request.user, public_id=public_id)
        except Event.DoesNotExist:
            raise Http404

    def get(self, request, public_id):
        return Response(_event_json(self._get(request, public_id), services.user_zone(request.user)))

    def delete(self, request, public_id):
        services.delete_event(user=request.user, event=self._get(request, public_id), request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PreferencesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        p = services.get_preferences(request.user)
        return Response({"timezone": p.timezone, "work_start": p.work_start.strftime("%H:%M"), "work_end": p.work_end.strftime("%H:%M"),
                         "work_days": p.work_days, "briefing_enabled": p.briefing_enabled,
                         "briefing_time": p.briefing_time.strftime("%H:%M")})

    def patch(self, request):
        serializer = PreferencesSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        prefs = services.get_preferences(request.user)
        # only the serializer's fields can ever be set
        for key, value in serializer.validated_data.items():
            setattr(prefs, key, value)
        prefs.save()
        return self.get(request)
