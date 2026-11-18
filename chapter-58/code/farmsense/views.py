"""REST endpoints. Every view asks the SAME function (farmsense_core.permissions.can) whether the caller may proceed.
NOT executed in the book's test environment."""
from datetime import datetime, timezone

from django.http import Http404
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from farmsense_core.permissions import can, can_assign_role, can_change_member, visible_sites

from .models import Alert, AlertState, DailyInsight, Membership, Sensor
from .readings_sql import bucketed


def membership_or_404(user, farm_id):
    m = Membership.objects.filter(user=user, farm_id=farm_id).first()
    if m is None:
        raise Http404                                        # a farm you do not belong to looks exactly like one that does not exist
    return m


class AlertAckView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, alert_id):
        alert = Alert.objects.select_related("rule__sensor__site").filter(pk=alert_id).first()
        if alert is None:
            raise Http404
        site = alert.rule.sensor.site
        m = membership_or_404(request.user, site.farm_id)
        if not can(m.to_core(), "alert.ack", site.id):
            return Response({"message": "You do not have permission to acknowledge alerts here."}, status=403)
        alert.acknowledged_by, alert.acknowledged_at = request.user, datetime.now(timezone.utc)
        alert.save(update_fields=["acknowledged_by", "acknowledged_at"])
        AlertState.objects.filter(rule=alert.rule).update(acknowledged=True)           # stops reminders and escalation
        return Response({"ok": True})


class ReadingsView(APIView):
    """GET /api/sensors/<id>/readings/?start=...&end=...&points=300  -> buckets, never raw points."""
    permission_classes = [IsAuthenticated]

    def get(self, request, sensor_id):
        sensor = Sensor.objects.select_related("site").filter(pk=sensor_id).first()
        if sensor is None:
            raise Http404
        m = membership_or_404(request.user, sensor.site.farm_id)
        if not can(m.to_core(), "dashboard.view", sensor.site_id):
            raise Http404                                    # do not reveal that the sensor exists
        start = datetime.fromisoformat(request.query_params["start"])
        end = datetime.fromisoformat(request.query_params["end"])
        if start.tzinfo is None or end.tzinfo is None or end <= start or (end - start).days > 93:
            return Response({"message": "start and end need a time zone, end after start, at most 93 days."}, status=400)
        points = min(max(int(request.query_params.get("points", 300)), 10), 1000)
        bucket = max(60, int((end - start).total_seconds() // points))
        rows = bucketed(sensor.id, start, end, bucket)
        return Response({"bucket_seconds": bucket, "buckets": [{"t": b.isoformat(), "n": n, "avg": a, "min": lo, "max": hi} for b, n, a, lo, hi in rows]})


class MemberRoleView(APIView):
    """PATCH {"role": "worker"} changes a member's role; DELETE removes them. Both go through the escalation rules."""
    permission_classes = [IsAuthenticated]

    def _target(self, request, farm_id, member_id):
        actor = membership_or_404(request.user, farm_id)
        target = Membership.objects.filter(pk=member_id, farm_id=farm_id).first()
        if target is None:
            raise Http404
        owners = Membership.objects.filter(farm_id=farm_id, role="owner").count()
        return actor.to_core(), target, owners

    def patch(self, request, farm_id, member_id):
        actor, target, owners = self._target(request, farm_id, member_id)
        new_role = request.data.get("role")
        if not (can_assign_role(actor, new_role) and can_change_member(actor, target.role, new_role, owners)):
            return Response({"message": "You cannot make this change."}, status=403)
        target.role = new_role
        target.save(update_fields=["role"])
        return Response({"ok": True})

    def delete(self, request, farm_id, member_id):
        actor, target, owners = self._target(request, farm_id, member_id)
        if not can_change_member(actor, target.role, None, owners):
            return Response({"message": "You cannot remove this member."}, status=403)
        target.delete()
        return Response(status=204)


class InsightView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, farm_id, day):
        m = membership_or_404(request.user, farm_id)
        if not can(m.to_core(), "insight.view"):
            raise Http404
        ins = DailyInsight.objects.filter(farm_id=farm_id, day=day).first()
        if ins is None:
            raise Http404
        return Response({"summary": ins.summary, "recommendations": ins.recommendations, "facts": ins.facts, "ai_generated": not ins.fallback,
                         "notice": "Suggestions are generated from the facts shown and are not professional advice."})


class PushTokenView(APIView):
    """The mobile app registers its Expo push token here after login. Idempotent: the same token twice is fine, and a token
    that moves to another account (shared phone) moves with it, so alerts never go to the previous user."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .models import PushToken
        token = str(request.data.get("token", ""))
        if not (token.startswith(("ExponentPushToken[", "ExpoPushToken[")) and token.endswith("]") and len(token) < 200):
            return Response({"message": "That is not an Expo push token."}, status=400)
        PushToken.objects.update_or_create(token=token, defaults={"user": request.user, "platform": str(request.data.get("platform", ""))[:10]})
        return Response({"ok": True})

    def delete(self, request):
        from .models import PushToken
        PushToken.objects.filter(user=request.user, token=request.data.get("token", "")).delete()      # call this on logout
        return Response(status=204)
