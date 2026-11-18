from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.security.crypto import verify_hmac

@csrf_exempt     # the provider cannot send a CSRF token; the signature is the proof
@require_POST
def provider_webhook(request):
    signature = request.headers.get("X-Signature", "")
    secret = settings.WEBHOOK_SIGNING_SECRET.encode()
    if not verify_hmac(secret, request.body, signature):
        return HttpResponse(status=401)    # no details: do not help tune a forgery
    # only now parse request.body, and process the event idempotently
    return HttpResponse(status=200)
