import ipaddress
import json
import secrets
import socket
from datetime import timedelta
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from . import signing
from .models import WebhookDelivery

BACKOFF = [
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=12),
]  # then we give up
MAX_ATTEMPTS = len(BACKOFF) + 1
TIMEOUT_SECONDS = 5


def validate_webhook_url(url: str):
    """Refuse URLs that would make OUR server call into private networks."""
    parts = urlparse(url)
    allowed = (
        ("https", "http") if settings.WEBHOOKS_ALLOW_HTTP else ("https",)
    )
    if parts.scheme not in allowed or not parts.hostname:
        raise ValidationError({"url": ["Use a public https:// address."]})
    if parts.username or parts.password:
        raise ValidationError({"url": ["Do not put credentials in the URL."]})
    try:
        addresses = {
            i[4][0]
            for i in socket.getaddrinfo(parts.hostname, parts.port or 443)
        }
    except socket.gaierror:
        raise ValidationError({"url": ["This host name does not resolve."]})
    for address in addresses:
        ip = ipaddress.ip_address(
            address
        )  # 10.x, 127.x, 169.254.x: not global
        if not (ip.is_global or settings.WEBHOOKS_ALLOW_PRIVATE):
            raise ValidationError({"url": ["This address is not allowed."]})


def new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(24)


def queue_event(user, event_type: str, data: dict):
    """Create one delivery per subscribed endpoint. Sending happens later."""
    envelope = {
        "type": event_type,
        "created_at": timezone.now().isoformat(),
        "data": data,
    }
    endpoints = user.endpoints.filter(is_active=True)
    return [
        WebhookDelivery.objects.create(
            endpoint=e, event_type=event_type, payload=envelope
        )
        for e in endpoints
        if "*" in e.events or event_type in e.events
    ]


def deliver(delivery: WebhookDelivery):
    """One attempt. Records the outcome and schedules a retry if it failed."""
    endpoint = delivery.endpoint
    body = json.dumps(
        {"id": str(delivery.event_id), **delivery.payload}
    ).encode()
    delivery.attempts += 1
    try:
        validate_webhook_url(endpoint.url)  # check again: DNS can change
        response = requests.post(
            endpoint.url,
            data=body,
            timeout=TIMEOUT_SECONDS,
            allow_redirects=False,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Id": str(delivery.event_id),
                "X-Webhook-Signature": signing.sign(endpoint.secret, body),
            },
        )
        delivery.last_status_code = response.status_code
        ok = 200 <= response.status_code < 300
        delivery.last_error = "" if ok else f"HTTP {response.status_code}"
    except (requests.RequestException, ValidationError) as exc:
        ok, delivery.last_error = False, type(exc).__name__
    if ok:
        delivery.status = WebhookDelivery.Status.SUCCEEDED
    elif delivery.attempts >= MAX_ATTEMPTS:
        delivery.status = WebhookDelivery.Status.FAILED
    else:
        delivery.next_attempt_at = (
            timezone.now() + BACKOFF[delivery.attempts - 1]
        )
    delivery.save()
    return ok


def deliver_due():
    """Attempt every pending delivery whose time has come."""
    due = WebhookDelivery.objects.filter(
        status="pending", next_attempt_at__lte=timezone.now()
    ).select_related("endpoint")
    return sum(deliver(d) for d in due[:100])
