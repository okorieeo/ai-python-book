from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from paystackbilling.errors import (AlreadySubscribed, ForbiddenReference, PaystackApiError, PaystackNetworkError,
                                    NoSubscription, UnknownPlan)
from paystackbilling.service import User as BillingUser
from paystackbilling.webhooks import source_ip_allowed

from .services import get_processor, get_service

ERRORS = {UnknownPlan: 400, AlreadySubscribed: 409, NoSubscription: 404, ForbiddenReference: 403,
          PaystackNetworkError: 503, PaystackApiError: 502}


def billing_user(request) -> BillingUser:
    u = request.user
    return BillingUser(str(u.pk), u.email, u.get_full_name())


class BillingView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "billing"

    def handle_exception(self, exc):
        for error, code in ERRORS.items():
            if isinstance(exc, error):
                return Response({"detail": str(exc)}, status=code)
        return super().handle_exception(exc)


def started(start):
    return Response({"reference": start.reference, "authorization_url": start.authorization_url,
                     "access_code": start.access_code})


class PayView(BillingView):
    def post(self, request):
        return started(get_service().start_payment(billing_user(request), request.data.get("plan", "")))


class SubscribeView(BillingView):
    def post(self, request):
        return started(get_service().start_subscription(billing_user(request), request.data.get("plan", "")))


class VerifyView(BillingView):
    def post(self, request):
        return Response(get_service().verify_payment(billing_user(request), request.data.get("reference", "")))


class StatusView(BillingView):
    def get(self, request):
        service, uid = get_service(), str(request.user.pk)
        d, record = service.access(uid), service.store.subscription_for(uid)
        return Response({"paid": d.paid, "tier": d.tier, "reason": d.reason, "until": d.until,
                         "status": record.status if record else None, "card_last4": record.card_last4 if record else "",
                         "switching_to": record.pending_plan_key if record else None,
                         "credits": service.store.credit_balance(uid)})


class CancelView(BillingView):
    def post(self, request):
        d = get_service().cancel(billing_user(request))
        return Response({"paid": d.paid, "reason": d.reason, "until": d.until})


class ResumeView(BillingView):
    def post(self, request):
        d = get_service().resume(billing_user(request))
        return Response({"paid": d.paid, "reason": d.reason})


class ChangePlanView(BillingView):
    def post(self, request):
        d = get_service().change_plan(billing_user(request), request.data.get("plan", ""))
        return Response({"paid": d.paid, "reason": d.reason})


class CardLinkView(BillingView):
    def post(self, request):
        return Response({"url": get_service().card_update_link(billing_user(request))})


@csrf_exempt                 # Paystack cannot send a CSRF token. The signature is the protection.
@require_POST
def paystack_webhook(request):
    """Use request.body (the raw bytes). Re-serializing the JSON would change the bytes and break the signature."""
    if getattr(settings, "PAYSTACK_ENFORCE_IPS", False):          # optional, as an extra layer only
        remote = request.META.get("REMOTE_ADDR", "")
        if not source_ip_allowed(remote, request.META.get("HTTP_X_FORWARDED_FOR", ""),
                                 trust_proxy=getattr(settings, "PAYSTACK_TRUST_PROXY", False)):
            return HttpResponse("forbidden", status=403)
    result = get_processor().handle(request.body, request.META.get("HTTP_X_PAYSTACK_SIGNATURE", ""))
    return HttpResponse(result.outcome, status=result.status)
