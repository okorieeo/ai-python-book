import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest import mock

import requests
from django.core import mail
from django.core.cache import cache
from django.db import transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User

from . import signing
from .models import (
    EmailSuppression,
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEvent,
)
from .outbound import MAX_ATTEMPTS, deliver, deliver_due, queue_event
from .emailing import send_templated_email

API = "/api/v1"
SECRET = "dev-secret"
PUBLIC_IP = [(2, 1, 6, "", ("93.184.216.34", 443))]  # what DNS would answer


def make_user(email="ada@example.com", **extra):
    return User.objects.create_user(
        email, "correct-horse-battery-staple", name="Ada <script>", **extra
    )


class EmailTests(APITestCase):
    def test_email_has_text_and_html_with_the_same_link(self):
        user = make_user()
        with self.captureOnCommitCallbacks(execute=True):
            send_templated_email(
                "verify_email",
                user.email,
                {"name": user.name, "link": "https://app.test/v?token=a&x=1"},
                subject="Verify your email",
            )
        message = mail.outbox[0]
        html = message.alternatives[0][0]
        self.assertIn(
            "https://app.test/v?token=a&x=1", message.body
        )  # text: as is
        self.assertIn("token=a&amp;x=1", html)  # html: escaped, still correct
        self.assertEqual(message.subject, "Verify your email")

    def test_user_supplied_text_is_escaped_in_html(self):
        user = make_user()
        with self.captureOnCommitCallbacks(execute=True):
            send_templated_email(
                "verify_email",
                user.email,
                {"name": user.name, "link": "https://app.test"},
                "Hi",
            )
        html = mail.outbox[0].alternatives[0][0]
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_nothing_is_sent_if_the_transaction_rolls_back(self):
        user = make_user()
        try:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with transaction.atomic():
                    send_templated_email(
                        "verify_email",
                        user.email,
                        {"name": "A", "link": "https://app.test"},
                        "Hi",
                    )
                    raise RuntimeError(
                        "something failed after queueing the email"
                    )
        except RuntimeError:
            pass
        self.assertEqual(len(mail.outbox), 0)

    def test_suppressed_addresses_are_never_emailed(self):
        EmailSuppression.objects.create(
            email="ada@example.com", reason="bounce"
        )
        with self.captureOnCommitCallbacks(execute=True):
            sent = send_templated_email(
                "verify_email",
                "Ada@Example.com",
                {"name": "A", "link": "https://app.test"},
                "Hi",
            )
        self.assertFalse(sent)
        self.assertEqual(len(mail.outbox), 0)


class InboundWebhookTests(APITestCase):
    def post_event(self, event, secret=SECRET, timestamp=None, header=None):
        body = json.dumps(event).encode()
        header = header or signing.sign(secret, body, timestamp)
        return self.client.post(
            API + "/webhooks/mailer",
            body,
            content_type="application/json",
            headers={"X-Webhook-Signature": header},
        )

    bounce = {
        "id": "evt_1",
        "type": "email.bounced",
        "data": {"email": "Gone@Example.com"},
    }

    def test_a_valid_bounce_suppresses_the_address(self):
        r = self.post_event(self.bounce)
        self.assertEqual((r.status_code, r.data["status"]), (200, "ok"))
        self.assertEqual(
            EmailSuppression.objects.get().email, "gone@example.com"
        )
        self.assertIsNotNone(WebhookEvent.objects.get().processed_at)

    def test_a_wrong_secret_or_tampered_body_is_rejected(self):
        self.assertEqual(
            self.post_event(self.bounce, secret="attacker").status_code, 400
        )
        body = json.dumps(self.bounce).encode()
        header = signing.sign(SECRET, body)
        forged = json.dumps(
            {**self.bounce, "data": {"email": "victim@example.com"}}
        ).encode()
        r = self.client.post(
            API + "/webhooks/mailer",
            forged,
            content_type="application/json",
            headers={"X-Webhook-Signature": header},
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(EmailSuppression.objects.count(), 0)

    def test_an_old_signed_request_cannot_be_replayed(self):
        r = self.post_event(self.bounce, timestamp=int(time.time()) - 3600)
        self.assertEqual(
            (r.status_code, r.data["error"]["code"]),
            (400, "invalid_signature"),
        )

    def test_missing_or_garbled_signature_headers_are_rejected(self):
        for header in ["", "garbage", "t=abc,v1=00"]:
            r = self.client.post(
                API + "/webhooks/mailer",
                b"{}",
                content_type="application/json",
                headers={"X-Webhook-Signature": header},
            )
            self.assertEqual(r.status_code, 400, header)

    def test_the_same_event_twice_is_processed_once(self):
        self.post_event(self.bounce)
        EmailSuppression.objects.all().delete()  # prove the 2nd call does no work
        r = self.post_event(self.bounce)
        self.assertEqual(
            (r.status_code, r.data["status"]), (200, "duplicate")
        )
        self.assertEqual(EmailSuppression.objects.count(), 0)
        self.assertEqual(WebhookEvent.objects.count(), 1)

    def test_unknown_event_types_are_stored_and_acknowledged(self):
        r = self.post_event(
            {"id": "evt_9", "type": "email.opened", "data": {}}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            WebhookEvent.objects.get().event_type, "email.opened"
        )


@override_settings(WEBHOOKS_ALLOW_HTTP=False)
class EndpointTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user(email_verified=True)
        self.client.force_authenticate(self.user)

    def create(
        self, url="https://hooks.example.com/in", events=("document.ready",)
    ):
        with mock.patch("socket.getaddrinfo", return_value=PUBLIC_IP):
            return self.client.post(
                API + "/webhook-endpoints",
                {"url": url, "events": list(events)},
                format="json",
            )

    def test_the_secret_is_shown_once_and_never_again(self):
        r = self.create()
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.data["secret"].startswith("whsec_"))
        listing = self.client.get(API + "/webhook-endpoints").data["results"][
            0
        ]
        self.assertNotIn("secret", listing)

    def test_urls_that_point_inside_our_network_are_refused(self):
        bad = {
            "http://hooks.example.com/in": PUBLIC_IP,  # not https
            "https://localhost/in": [(2, 1, 6, "", ("127.0.0.1", 443))],
            "https://internal.example.com": [
                (2, 1, 6, "", ("10.0.0.5", 443))
            ],
            "https://metadata.example.com": [
                (2, 1, 6, "", ("169.254.169.254", 443))
            ],
            "https://user:pw@hooks.example.com/in": PUBLIC_IP,  # credentials
        }
        for url, dns in bad.items():
            with mock.patch("socket.getaddrinfo", return_value=dns):
                r = self.client.post(
                    API + "/webhook-endpoints",
                    {"url": url, "events": ["*"]},
                    format="json",
                )
            self.assertEqual(r.status_code, 422, url)
        self.assertEqual(WebhookEndpoint.objects.count(), 0)

    def test_unknown_events_and_unverified_users_are_refused(self):
        self.assertEqual(self.create(events=("made.up",)).status_code, 422)
        self.user.email_verified = False
        self.user.save()
        self.assertEqual(self.create().status_code, 403)

    def test_endpoints_belong_to_their_owner(self):
        public_id = self.create().data["id"]
        self.client.force_authenticate(
            make_user("bo@example.com", email_verified=True)
        )
        self.assertEqual(
            self.client.delete(
                f"{API}/webhook-endpoints/{public_id}"
            ).status_code,
            404,
        )


@override_settings(WEBHOOKS_ALLOW_HTTP=False)
class DeliveryTests(APITestCase):
    def setUp(self):
        self.user = make_user(email_verified=True)
        self.endpoint = WebhookEndpoint.objects.create(
            user=self.user,
            url="https://hooks.example.com/in",
            secret="whsec_test",
            events=["document.ready"],
        )
        patcher = mock.patch("socket.getaddrinfo", return_value=PUBLIC_IP)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_events_go_only_to_subscribed_endpoints(self):
        self.assertEqual(
            len(queue_event(self.user, "document.ready", {"id": "d1"})), 1
        )
        self.assertEqual(
            len(queue_event(self.user, "message.created", {})), 0
        )

    def test_a_delivery_is_signed_so_the_receiver_can_verify_it(self):
        (delivery,) = queue_event(self.user, "document.ready", {"id": "d1"})
        with mock.patch(
            "requests.post", return_value=mock.Mock(status_code=200)
        ) as post:
            self.assertTrue(deliver(delivery))
        kwargs = post.call_args.kwargs
        self.assertFalse(
            kwargs["allow_redirects"]
        )  # a redirect could bypass our checks
        self.assertEqual(kwargs["timeout"], 5)
        body, header = (
            kwargs["data"],
            kwargs["headers"]["X-Webhook-Signature"],
        )
        self.assertTrue(
            signing.verify("whsec_test", body, header, 300)
        )  # the receiver's job
        self.assertFalse(signing.verify("another-secret", body, header, 300))
        self.assertEqual(json.loads(body)["type"], "document.ready")
        delivery.refresh_from_db()
        self.assertEqual(
            (delivery.status, delivery.attempts), ("succeeded", 1)
        )

    def test_failures_are_retried_with_growing_delays_then_abandoned(self):
        (delivery,) = queue_event(self.user, "document.ready", {})
        waits = []
        with mock.patch(
            "requests.post", return_value=mock.Mock(status_code=500)
        ):
            for _ in range(MAX_ATTEMPTS):
                before = timezone.now()
                deliver(delivery)
                waits.append(
                    (delivery.next_attempt_at - before).total_seconds()
                )
        self.assertEqual(delivery.status, "failed")
        self.assertEqual(delivery.attempts, MAX_ATTEMPTS)
        self.assertEqual(delivery.last_error, "HTTP 500")
        self.assertTrue(
            all(b > a for a, b in zip(waits[:4], waits[1:5]))
        )  # 1m, 5m, 30m...

    def test_network_errors_count_as_failures(self):
        (delivery,) = queue_event(self.user, "document.ready", {})
        with mock.patch("requests.post", side_effect=requests.Timeout):
            self.assertFalse(deliver(delivery))
        delivery.refresh_from_db()
        self.assertEqual(
            (delivery.status, delivery.last_error), ("pending", "Timeout")
        )

    def test_only_due_deliveries_are_sent(self):
        due, later = (
            queue_event(self.user, "document.ready", {})[0] for _ in range(2)
        )
        WebhookDelivery.objects.filter(pk=later.pk).update(
            next_attempt_at=timezone.now() + timedelta(hours=1)
        )
        with mock.patch(
            "requests.post", return_value=mock.Mock(status_code=204)
        ) as post:
            self.assertEqual(deliver_due(), 1)
        self.assertEqual(post.call_count, 1)

    def test_the_address_is_checked_again_at_delivery_time(self):
        (delivery,) = queue_event(self.user, "document.ready", {})
        private = [
            (2, 1, 6, "", ("10.0.0.5", 443))
        ]  # DNS now points inside our network
        with mock.patch(
            "socket.getaddrinfo", return_value=private
        ), mock.patch("requests.post") as post:
            self.assertFalse(deliver(delivery))
        post.assert_not_called()
