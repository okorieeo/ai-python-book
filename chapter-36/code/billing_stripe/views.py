import time

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from stripebilling.errors import (AlreadySubscribed, ForbiddenSession, NoCustomer, NoSubscription, UnknownPlan)
from stripebilling.params import idempotency_key, payment_intent_params
from stripebilling.service import User as BillingUser

from .services import get_processor, get_service

ERRORS = {UnknownPlan: 400, AlreadySubscribed: 409, NoCustomer: 409, NoSubscription: 404, ForbiddenSession: 403}


def billing_user(request) -> BillingUser:
    u = request.user
    return BillingUser(str(u.pk), u.email, u.get_full_name())


class BillingView(APIView):
    """Base class: login required, throttled, and billing errors become clean HTTP answers."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "billing"

    def handle_exception(self, exc):
        for error, code in ERRORS.items():
            if isinstance(exc, error):
                return Response({"detail": str(exc)}, status=code)
        return super().handle_exception(exc)


class CheckoutView(BillingView):
    def post(self, request):
        start = get_service().start_checkout(billing_user(request), request.data.get("plan", ""),
                                             embedded=bool(request.data.get("embedded")))
        return Response({"session_id": start.session_id, "url": start.url, "client_secret": start.client_secret})


class SyncView(BillingView):
    def post(self, request):
        return Response(get_service().sync_checkout(billing_user(request), request.data.get("session_id", "")))


class PortalView(BillingView):
    def post(self, request):
        return Response({"url": get_service().open_portal(billing_user(request))})


class StatusView(BillingView):
    def get(self, request):
        service = get_service()
        decision = service.access(str(request.user.pk))
        record = service.store.subscription_for(str(request.user.pk))
        return Response({"paid": decision.paid, "tier": decision.tier, "reason": decision.reason, "until": decision.until,
                         "status": record.status if record else None,
                         "credits": service.store.credit_balance(str(request.user.pk))})


class ChangePlanView(BillingView):
    def post(self, request):
        d = get_service().change_plan(billing_user(request), request.data.get("plan", ""))
        return Response({"paid": d.paid, "tier": d.tier, "reason": d.reason})


class CancelView(BillingView):
    def post(self, request):
        d = get_service().cancel(billing_user(request), immediately=bool(request.data.get("immediately")))
        return Response({"paid": d.paid, "tier": d.tier, "reason": d.reason, "until": d.until})


class ResumeView(BillingView):
    def post(self, request):
        d = get_service().resume(billing_user(request))
        return Response({"paid": d.paid, "tier": d.tier, "reason": d.reason})


@csrf_exempt                      # Stripe cannot send a CSRF token; the signature is the protection
@require_POST
def stripe_webhook(request):
    """Use request.body (the raw bytes). Re-serializing the JSON would change the bytes and break the signature."""
    result = get_processor().handle(request.body, request.META.get("HTTP_STRIPE_SIGNATURE", ""))
    return HttpResponse(result.outcome, status=result.status)


# What the mobile app may buy with the Payment Sheet. The amounts live HERE, on the server.
# Only real-world goods and services belong in this table (see the store-rules box in section 36.9).
MOBILE_CATALOG = {"consulting_hour": {"amount": 15000, "currency": "usd", "description": "One hour of consulting"}}


class PaymentSheetView(BillingView):
    """Creates what the mobile Payment Sheet needs: a PaymentIntent, an ephemeral key and the customer id."""

    def post(self, request):
        item = MOBILE_CATALOG.get(request.data.get("item", ""))
        if item is None:
            return Response({"detail": "Unknown item."}, status=400)
        service, user = get_service(), billing_user(request)
        customer = service.customer_id(user)
        intent = service.gateway.create_payment_intent(
            payment_intent_params(customer_id=customer, user_id=user.id, **item),
            idempotency_key("pi", user.id, request.data["item"], int(time.time() // 300)))
        key = service.gateway.create_ephemeral_key(customer, settings.STRIPE_MOBILE_API_VERSION)
        return Response({"paymentIntent": intent["client_secret"], "ephemeralKey": key["secret"],
                         "customer": customer, "publishableKey": settings.STRIPE_PUBLISHABLE_KEY},
                        status=status.HTTP_201_CREATED)
