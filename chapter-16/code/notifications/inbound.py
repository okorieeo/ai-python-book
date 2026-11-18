import json

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import signing
from .models import EmailSuppression, WebhookEvent


def handle_email_event(event):
    """React to what the email provider tells us about a message."""
    address = event.payload.get("data", {}).get("email", "").lower()
    if event.event_type in ("email.bounced", "email.complained") and address:
        reason = (
            "bounce" if event.event_type == "email.bounced" else "complaint"
        )
        EmailSuppression.objects.get_or_create(
            email=address, defaults={"reason": reason}
        )
    # "email.delivered" and unknown types: nothing to do, but we keep the record


class MailerWebhook(APIView):
    """POST /webhooks/mailer: events from our email provider."""

    permission_classes = [AllowAny]
    authentication_classes = []  # the signature is the authentication

    def post(self, request):
        body = (
            request.body
        )  # the exact bytes that were signed: read them first
        header = request.headers.get("X-Webhook-Signature", "")
        if not signing.verify(
            settings.MAILER_WEBHOOK_SECRET,
            body,
            header,
            settings.WEBHOOK_TOLERANCE_SECONDS,
        ):
            return Response(
                {
                    "error": {
                        "code": "invalid_signature",
                        "message": "Signature check failed.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            data = json.loads(body)
            event_id, event_type = str(data["id"]), str(data["type"])
        except (ValueError, KeyError, TypeError):
            return Response(
                {
                    "error": {
                        "code": "invalid_payload",
                        "message": "Malformed event.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                event = WebhookEvent.objects.create(
                    provider="mailer",
                    event_id=event_id,
                    event_type=event_type,
                    payload=data,
                )
        except (
            IntegrityError
        ):  # we already have this event: say "got it" again
            return Response({"status": "duplicate"})
        handle_email_event(
            event
        )  # in production: queue a Celery task instead
        event.processed_at = timezone.now()
        event.save(update_fields=["processed_at"])
        return Response({"status": "ok"})
