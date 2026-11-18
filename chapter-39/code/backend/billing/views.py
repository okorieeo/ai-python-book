import time

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .endpoint import WebhookConfig, handle_webhook_request
from .handlers import BillingState, build_handlers
from .stores import DbIdempotencyStore


# DEMO ONLY: in-memory state, lost on restart and not shared between processes. In your project, build the
# handlers from the services you wrote in Chapters 35 to 38, so they update your real billing tables.
HANDLERS = build_handlers(BillingState())


def _config() -> WebhookConfig:
    return WebhookConfig(stripe_secrets=tuple(settings.STRIPE_WEBHOOK_SECRETS), paystack_secret=settings.PAYSTACK_SECRET_KEY)


@csrf_exempt          # the signature IS the authentication: a browser-based CSRF token cannot apply to a provider
@require_POST
def webhook(request, provider: str):
    status, body = handle_webhook_request(
        provider, request.headers, request.body,              # request.body: the RAW bytes. Never re-serialise parsed JSON
        config=_config(), store=DbIdempotencyStore(), handlers=HANDLERS, now=time.time())
    return JsonResponse(body, status=status)
