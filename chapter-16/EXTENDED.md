# Chapter 16 — File Handling, Storage and Email: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Configuring Storage in Django › Local S3 with MinIO (optional)

To rehearse the production setup on your laptop, add MinIO to the Docker setup from Chapter 2, create a bucket in its web console at `http://localhost:9001`, and point the variables above at `http://localhost:9000`.

**docker-compose.yml (excerpt)**

```
services:
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio-data:/data

volumes:
  minio-data:
```

> **Keep the bucket private**
>
> Every cloud provider lets you make a bucket public. For user documents, **never** do. Keep the bucket private and give access only through short-lived signed URLs that your API creates after checking who is asking. Several well-known data breaches were simply public buckets full of customer files.


## Uploads Through Your Server › Tests

**documents/tests.py**

```
import io
import shutil
import tempfile

import boto3
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from django.test import override_settings
from moto import mock_aws
from PIL import Image
from rest_framework.test import APITestCase

from accounts.models import User

from .models import Document

API = "/api/v1"
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
EXE = b"MZ\x90\x00\x03\x00\x00\x00 this is not a pdf"

def upload_file(name, data):
    return SimpleUploadedFile(name, data)

class FileTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.user = User.objects.create_user(
            "ada@example.com", "correct-horse-battery-staple", name="Ada"
        )
        self.client.force_authenticate(self.user)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def post_file(self, name="notes.pdf", data=PDF, path="/documents"):
        return self.client.post(
            API + path, {"file": upload_file(name, data)}, format="multipart"
        )

class UploadTests(FileTestCase):
    def test_a_pdf_is_stored_under_a_key_we_choose(self):
        r = self.post_file("../../etc/Quarterly report.pdf")
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.data["status"], "uploaded")
        self.assertEqual(
            r.data["filename"], "Quarterly report.pdf"
        )  # path removed
        doc = Document.objects.get()
        self.assertTrue(
            doc.storage_key.startswith(f"documents/{self.user.public_id}/")
        )
        self.assertNotIn(
            "Quarterly", doc.storage_key
        )  # the name is not in the path
        self.assertNotIn("storage_key", r.data)

    def test_the_content_decides_the_type_not_the_filename(self):
        r = self.post_file(
            "invoice.pdf", EXE
        )  # an executable renamed to .pdf
        self.assertEqual(
            (r.status_code, r.data["error"]["code"]),
            (415, "unsupported_file_type"),
        )
        self.assertEqual(Document.objects.count(), 0)
        png = io.BytesIO()
        Image.new("RGB", (4, 4)).save(png, "PNG")
        r = self.post_file("photo.txt", png.getvalue())  # a PNG named .txt
        self.assertEqual(Document.objects.get().content_type, "image/png")

    def test_empty_and_oversized_files_are_refused(self):
        self.assertEqual(self.post_file(data=b"").status_code, 422)
        with override_settings(UPLOAD_MAX_BYTES=1000):
            r = self.post_file(data=PDF + b"x" * 2000)
        self.assertEqual(
            (r.status_code, r.data["error"]["code"]), (413, "file_too_large")
        )

    def test_missing_file_field_returns_validation_error(self):
        r = self.client.post(API + "/documents", {}, format="multipart")
        self.assertEqual(r.status_code, 422)

    def test_uploading_the_same_file_twice_stores_it_once(self):
        first = self.post_file("a.pdf")
        second = self.post_file("copy-of-a.pdf")
        self.assertEqual((first.status_code, second.status_code), (202, 200))
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Document.objects.count(), 1)

    def test_storage_quota_is_enforced(self):
        with override_settings(UPLOAD_QUOTA_BYTES=len(PDF) + 5):
            self.assertEqual(self.post_file("a.pdf").status_code, 202)
            r = self.post_file("b.pdf", PDF + b"different")
        self.assertEqual(
            (r.status_code, r.data["error"]["code"]),
            (403, "storage_quota_exceeded"),
        )

    def test_uploads_are_throttled(self):
        for i in range(60):
            self.post_file(data=PDF + str(i).encode())
        r = self.post_file(data=PDF + b"one-too-many")
        self.assertEqual(r.status_code, 429)

class AccessTests(FileTestCase):
    def test_files_belong_to_their_owner(self):
        doc_id = self.post_file().data["id"]
        other = User.objects.create_user(
            "bo@example.com", "correct-horse-battery-staple", name="Bo"
        )
        self.client.force_authenticate(other)
        for method, url in [
            ("get", f"/documents/{doc_id}"),
            ("get", f"/documents/{doc_id}/download"),
            ("delete", f"/documents/{doc_id}"),
        ]:
            self.assertEqual(
                getattr(self.client, method)(API + url).status_code, 404, url
            )
        self.assertEqual(self.client.get(API + "/documents").data["count"], 0)

    def test_download_streams_the_file_as_an_attachment(self):
        doc_id = self.post_file("notes.pdf").data["id"]
        r = self.client.get(f"{API}/documents/{doc_id}/download")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), PDF)
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")

    def test_delete_removes_the_file_and_the_row(self):
        doc_id = self.post_file().data["id"]
        key = Document.objects.get().storage_key
        self.assertEqual(
            self.client.delete(f"{API}/documents/{doc_id}").status_code, 204
        )
        from django.core.files.storage import storages

        self.assertFalse(storages["default"].exists(key))
        self.assertEqual(Document.objects.count(), 0)

    def test_login_is_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(API + "/documents").status_code, 401)
```

`FileTestCase` points `MEDIA_ROOT` at a temporary folder for each test and deletes it afterwards, so tests never touch real files. `test_the_content_decides_the_type_not_the_filename` is the most important: an executable named `invoice.pdf` is refused, and a PNG named `photo.txt` is stored as a PNG.


## Direct Uploads with Signed URLs › Tests with a simulated S3

The `moto` library pretends to be Amazon S3 inside the test process. The tests below switch the project to the S3 storage backend, create an in-memory bucket, and exercise the real code paths, including a client that lies about what it uploaded.

**documents/tests.py (add)**

```
S3_SETTINGS = {
    "bucket_name": "test-bucket",
    "endpoint_url": None,
    "region_name": "us-east-1",
    "access_key": "testing",
    "secret_key": "testing",
}

S3_STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **S3_SETTINGS,
            "signature_version": "s3v4",
            "querystring_auth": True,
            "querystring_expire": 300,
            "file_overwrite": False,
        },
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

@override_settings(S3=S3_SETTINGS, STORAGES=S3_STORAGES)
class S3Tests(FileTestCase):
    def setUp(self):
        super().setUp()
        self.mock = mock_aws()
        self.mock.start()
        self.s3 = boto3.client("s3", region_name="us-east-1")
        self.s3.create_bucket(Bucket="test-bucket")

    def tearDown(self):
        self.mock.stop()
        super().tearDown()

    def test_upload_through_the_api_lands_in_the_bucket(self):
        r = self.post_file()
        self.assertEqual(r.status_code, 202)
        key = Document.objects.get().storage_key
        self.assertEqual(
            self.s3.get_object(Bucket="test-bucket", Key=key)["Body"].read(),
            PDF,
        )

    def test_download_redirects_to_a_signed_expiring_url(self):
        doc_id = self.post_file().data["id"]
        r = self.client.get(f"{API}/documents/{doc_id}/download")
        self.assertEqual(r.status_code, 302)
        self.assertIn("X-Amz-Signature", r["Location"])
        self.assertIn("X-Amz-Expires=300", r["Location"])

    def start_direct(self, **extra):
        body = {
            "filename": "big.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(PDF),
        }
        return self.client.post(
            API + "/documents/upload-url", {**body, **extra}, format="json"
        )

    def test_direct_upload_flow(self):
        step1 = self.start_direct()
        self.assertEqual(step1.status_code, 201)
        self.assertIn("X-Amz-Signature", step1.data["upload_url"])
        from django.core import signing

        key = signing.loads(step1.data["upload_token"], salt="direct-upload")[
            "key"
        ]
        self.s3.put_object(
            Bucket="test-bucket", Key=key, Body=PDF
        )  # the browser's PUT
        done = self.client.post(
            API + "/documents/complete",
            {"upload_token": step1.data["upload_token"]},
            format="json",
        )
        self.assertEqual(
            (done.status_code, done.data["status"]), (202, "uploaded")
        )
        self.assertEqual(Document.objects.get().size_bytes, len(PDF))

    def test_a_lying_client_is_caught_at_completion(self):
        step1 = self.start_direct()
        from django.core import signing

        key = signing.loads(step1.data["upload_token"], salt="direct-upload")[
            "key"
        ]
        self.s3.put_object(
            Bucket="test-bucket", Key=key, Body=EXE
        )  # not a PDF at all
        done = self.client.post(
            API + "/documents/complete",
            {"upload_token": step1.data["upload_token"]},
            format="json",
        )
        self.assertEqual(done.status_code, 415)
        self.assertEqual(Document.objects.count(), 0)
        keys = self.s3.list_objects_v2(Bucket="test-bucket").get(
            "Contents", []
        )
        self.assertEqual(keys, [])  # the rejected object was deleted

    def test_completion_without_an_upload_and_with_bad_tokens(self):
        step1 = self.start_direct()
        token = step1.data["upload_token"]
        r = self.client.post(
            API + "/documents/complete",
            {"upload_token": token},
            format="json",
        )
        self.assertEqual(r.status_code, 422)  # nothing was uploaded yet
        r = self.client.post(
            API + "/documents/complete",
            {"upload_token": token + "x"},
            format="json",
        )
        self.assertEqual(
            (r.status_code, r.data["error"]["code"]), (400, "invalid_token")
        )
        other = User.objects.create_user(
            "bo@example.com", "correct-horse-battery-staple", name="Bo"
        )
        self.client.force_authenticate(other)
        r = self.client.post(
            API + "/documents/complete",
            {"upload_token": token},
            format="json",
        )
        self.assertEqual(
            r.status_code, 400
        )  # a token only works for its owner

    def test_upload_url_refuses_bad_declarations(self):
        self.assertEqual(
            self.start_direct(size_bytes=50 * 1024 * 1024).status_code, 413
        )
        self.assertEqual(
            self.start_direct(
                content_type="application/x-msdownload"
            ).status_code,
            422,
        )
```


## Transactional Email and Templates › Test emails locally

The console backend is enough for logic, but to *see* the HTML, run a local mail catcher such as Mailpit in Docker, set `EMAIL_HOST=localhost` and `EMAIL_PORT=1025` (with `use_tls` off in development), and open its web page to inspect every message.


## Transactional Email and Templates › Tests

**notifications/tests.py**

```
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
```

The rollback test is the one to remember: it proves that an email queued inside a failed transaction is never sent. Django’s `captureOnCommitCallbacks` lets a test run those callbacks as if the transaction had committed. The Chapter 13 tests needed one change to keep working: their base class patches `on_commit` to run immediately, because Django’s `TestCase` never commits.


## Receiving Webhooks › Tests

**notifications/tests.py (add)**

```
SECRET = "dev-secret"

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
```

Read the second test slowly. It signs one body and sends a different body with that signature (a forgery) and proves nothing is stored. The third proves that an old but correctly signed request is refused: that is replay protection.


## Sending Webhooks to Your Customers › Tests

**notifications/tests.py (add)**

```
PUBLIC_IP = [(2, 1, 6, "", ("93.184.216.34", 443))]  # what DNS would answer

def make_user(email="ada@example.com", **extra):
    return User.objects.create_user(
        email, "correct-horse-battery-staple", name="Ada <script>", **extra
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
```

Four tests deserve attention. `test_urls_that_point_inside_our_network_are_refused` walks through every SSRF case, including a cloud metadata address. `test_a_delivery_is_signed_so_the_receiver_can_verify_it` plays the customer’s part and verifies our signature. `test_failures_are_retried_with_growing_delays_then_abandoned` checks the whole retry schedule. And `test_the_address_is_checked_again_at_delivery_time` simulates a host name that started pointing at a private address after registration.
