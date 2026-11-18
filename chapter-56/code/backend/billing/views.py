import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from chat.usage import get_quota

from .entitlements import current_plan
from .gateways.base import GatewayError, InvalidSignature
from .gateways.registry import UnknownGateway, get_gateway
from .models import Plan, Subscription
from .services import apply_event

logger = logging.getLogger(__name__)


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["code", "name", "daily_message_limit", "price_usd_cents"]


class PlanListView(APIView):
    permission_classes = [AllowAny]  # the pricing page is public

    def get(self, request):
        return Response(PlanSerializer(Plan.objects.filter(is_public=True), many=True).data)


class SubscriptionView(APIView):
    def get(self, request):
        plan = current_plan(request.user)
        sub = Subscription.objects.filter(user=request.user).first()
        quota = get_quota(request.user, plan.daily_message_limit)
        return Response({
            "plan": PlanSerializer(plan).data,
            "status": sub.status if sub else "none",
            "gateway": sub.gateway if sub else "",
            "current_period_end": sub.current_period_end if sub else None,
            "cancel_at_period_end": sub.cancel_at_period_end if sub else False,
            "usage": {"used": quota.used, "limit": quota.limit},
        })


class CheckoutSerializer(serializers.Serializer):
    plan = serializers.SlugField()
    gateway = serializers.ChoiceField(choices=["stripe", "paystack"])


class CheckoutView(APIView):
    throttle_scope = "checkout"

    def post(self, request):
        data = CheckoutSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        plan = Plan.objects.filter(code=data.validated_data["plan"], is_public=True).first()
        if plan is None or not plan.is_paid:
            return Response({"detail": "Unknown plan."}, status=404)
        if current_plan(request.user).is_paid:
            return Response({"detail": "You already have a paid plan. Use the billing portal to change it."},
                            status=409)
        try:
            gateway = get_gateway(data.validated_data["gateway"])
            session = gateway.create_checkout(
                user=request.user, plan=plan,
                success_url=f"{settings.FRONTEND_URL}/billing?checkout=success",
                cancel_url=f"{settings.FRONTEND_URL}/billing?checkout=cancelled")
        except UnknownGateway:
            return Response({"detail": "That payment method is not available."}, status=400)
        except GatewayError:
            logger.exception("checkout failed for user %s", request.user.pk)
            return Response({"detail": "We could not start checkout. Please try again."}, status=502)
        return Response({"url": session.url})


class PortalView(APIView):
    def post(self, request):
        sub = Subscription.objects.filter(user=request.user).first()
        if sub is None or not sub.gateway:
            return Response({"detail": "You do not have a subscription."}, status=404)
        try:
            url = get_gateway(sub.gateway).manage_url(subscription=sub, return_url=f"{settings.FRONTEND_URL}/billing")
        except (UnknownGateway, GatewayError):
            return Response({"detail": "The billing portal is unavailable right now."}, status=502)
        return Response({"url": url})


@csrf_exempt  # the gateway has no CSRF token; the signature is the authentication
@require_POST
def webhook(request, provider: str):
    try:
        gateway = get_gateway(provider)
    except UnknownGateway:
        return HttpResponse(status=404)
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        event = gateway.parse_webhook(body=request.body, headers=headers)  # raw bytes, before any JSON parsing
    except InvalidSignature:
        return HttpResponse(status=400)
    if event is None:
        return HttpResponse(status=200)  # an event type we do not use: acknowledge so it is not retried
    try:
        outcome = apply_event(event)
    except Exception:
        logger.exception("failed to apply %s event %s", provider, event.event_id)
        return HttpResponse(status=500)  # the gateway will retry
    return JsonResponse({"outcome": outcome})
