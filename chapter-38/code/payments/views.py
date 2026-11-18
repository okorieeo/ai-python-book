from django.http import HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.payments.checkout import CheckoutFailed

from . import services
from .models import Payment


class CheckoutSerializer(serializers.Serializer):
    plan_code = serializers.SlugField(max_length=40)
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    country = serializers.RegexField(r"^[A-Z]{2}$", required=False, allow_null=True)
    preferred = serializers.ChoiceField(choices=["stripe", "paystack"], required=False, allow_null=True)


class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "checkout"

    def post(self, request):
        key = request.headers.get("Idempotency-Key", "")
        if not 8 <= len(key) <= 80:
            return Response({"detail": "Send an Idempotency-Key header (8 to 80 characters)."}, status=400)
        data = CheckoutSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            record = services.begin_checkout(user=request.user, idempotency_key=key, **data.validated_data)
        except CheckoutFailed as exc:
            code = 503 if exc.retry_same_key else 400
            return Response({"detail": str(exc), "retry_with_same_key": exc.retry_same_key}, status=code)
        return Response({"payment_id": record.reference, "provider": record.provider, "redirect_url": record.redirect_url},
                        status=status.HTTP_201_CREATED)


class PaymentStatusView(APIView):
    """The frontend polls this after the redirect. It never trusts the redirect itself."""
    permission_classes = [IsAuthenticated]

    def get(self, request, reference):
        payment = Payment.objects.filter(reference=reference, user=request.user).first()   # owner-scoped (Chapter 17)
        if payment is None:
            return Response(status=404)
        return Response({"status": payment.status, "amount_minor": payment.amount_minor, "currency": payment.currency})


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):
    """Plain Django view: we need the exact raw bytes, and the gateway cannot send a CSRF token or a login."""
    provider = ""

    def post(self, request):
        headers = {k.lower().replace("_", "-").removeprefix("http-"): v for k, v in request.META.items() if k.startswith("HTTP_")}
        # With a proxy in front, resolve the real client IP with Chapter 17's trusted-proxy helper instead.
        headers["x-client-ip"] = request.META.get("REMOTE_ADDR", "")
        code, outcome = services.handle_webhook(self.provider, request.body, headers)
        return HttpResponse(outcome, status=code, content_type="text/plain")


class StripeWebhookView(WebhookView):
    provider = "stripe"


class PaystackWebhookView(WebhookView):
    provider = "paystack"
