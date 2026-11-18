import json
import time

import pytest

from billing.models import ProcessedWebhookEvent
from testsupport.signing import paystack_event, paystack_headers, stripe_event, stripe_headers, to_bytes

URL = "/api/v1/webhooks/{}/"
EVENT = stripe_event("evt_view_1", "customer.subscription.deleted", {"metadata": {"user_id": "7"}})


def post(client, provider, body, headers):
    meta = {"HTTP_" + k.upper().replace("-", "_"): v for k, v in headers.items() if k != "Content-Type"}
    return client.post(URL.format(provider), data=body, content_type="application/json", **meta)


@pytest.mark.django_db
def test_a_signed_event_is_stored_once_in_the_database(client, settings):
    body = to_bytes(EVENT)
    headers = stripe_headers(body, settings.STRIPE_WEBHOOK_SECRETS[0], int(time.time()))
    assert post(client, "stripe", body, headers).status_code == 200
    assert post(client, "stripe", body, headers).json() == {"status": "duplicate"}
    assert ProcessedWebhookEvent.objects.filter(key="stripe:evt_view_1").count() == 1


@pytest.mark.django_db
def test_an_unsigned_request_changes_nothing(client):
    res = client.post(URL.format("stripe"), data=to_bytes(EVENT), content_type="application/json")
    assert res.status_code == 400
    assert ProcessedWebhookEvent.objects.count() == 0


@pytest.mark.django_db
def test_get_is_not_allowed(client):
    assert client.get(URL.format("stripe")).status_code == 405


@pytest.mark.django_db
def test_paystack_signature_uses_the_raw_body(client, settings):
    event = paystack_event("customer.identification.success", {"id": 5})
    body = to_bytes(event)
    headers = paystack_headers(body, settings.PAYSTACK_SECRET_KEY)
    assert post(client, "paystack", body, headers).status_code == 200
