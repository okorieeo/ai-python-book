import logging
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone
from kombu.exceptions import OperationalError
from rest_framework.test import APITestCase

from accounts.models import User
from chat import services, tasks
from chat.models import (Conversation, Document, IdempotencyKey, Message,
                         UsageRecord)
from config.celery import app as celery_app

FAST = {"FAKE_PROCESSING_SECONDS": 0,
        "PASSWORD_HASHERS": ["django.contrib.auth.hashers.MD5PasswordHasher"]}

class CeleryTestMixin:
    """Run tasks immediately, in-process: no Redis, no worker needed."""

    def setUp(self):
        super().setUp()
        celery_app.conf.task_always_eager = True
        self.addCleanup(setattr, celery_app.conf, "task_always_eager", False)
        logging.disable(logging.CRITICAL)          # expected failures are noisy
        self.addCleanup(logging.disable, logging.NOTSET)
        self.ada = User.objects.create_user("ada", "ada@example.com", "pw-ada-1")

    def make_doc(self, filename, status=Document.Status.PROCESSING):
        return Document.objects.create(user=self.ada, filename=filename,
                                       status=status)

@override_settings(**FAST)
class IngestTaskTests(CeleryTestMixin, TestCase):
    def test_success_marks_ready_and_counts_chunks(self):
        doc = self.make_doc("report.pdf")
        result = tasks.ingest_document.delay(doc.pk)
        doc.refresh_from_db()
        self.assertEqual(result.get(), "ready:3")
        self.assertEqual((doc.status, doc.chunk_count), ("ready", 3))

    def test_a_duplicate_delivery_is_harmless(self):
        doc = self.make_doc("report.pdf")
        tasks.ingest_document.delay(doc.pk)
        again = tasks.ingest_document.delay(doc.pk)
        self.assertEqual(again.get(), "skipped")      # already ready: no rework

    def test_a_deleted_document_is_skipped(self):
        doc = self.make_doc("report.pdf")
        pk = doc.pk
        doc.delete()
        self.assertEqual(tasks.ingest_document.delay(pk).get(), "skipped")

    def test_temporary_errors_are_retried_until_they_work(self):
        doc = self.make_doc("flaky.pdf")              # fails twice, then works
        tasks.ingest_document.delay(doc.pk)
        doc.refresh_from_db()
        self.assertEqual(doc.status, "ready")

    def test_gives_up_after_the_last_retry(self):
        doc = self.make_doc("timeout.pdf")            # never works
        tasks.ingest_document.delay(doc.pk)
        doc.refresh_from_db()
        self.assertEqual(doc.status, "failed")
        self.assertIn("Gave up", doc.error)

    def test_permanent_errors_fail_at_once_without_retrying(self):
        doc = self.make_doc("corrupt.pdf")
        with mock.patch.object(tasks, "extract_chunks",
                               wraps=tasks.extract_chunks) as spy:
            tasks.ingest_document.delay(doc.pk)
        doc.refresh_from_db()
        self.assertEqual((doc.status, spy.call_count), ("failed", 1))
        self.assertEqual(doc.error, "The file could not be read.")

@override_settings(**FAST)
class EnqueueTests(CeleryTestMixin, APITestCase):
    def login(self):
        reply = self.client.post("/api/v1/auth/login",
                                 {"username": "ada", "password": "pw-ada-1"})
        token = reply.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_the_job_is_queued_only_after_the_transaction_commits(self):
        self.login()
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            reply = self.client.post("/api/v1/documents",
                                     {"filename": "report.pdf"})
        doc = Document.objects.get(public_id=reply.data["id"])
        self.assertEqual((reply.status_code, len(callbacks)), (202, 1))
        self.assertEqual(doc.status, "processing")    # nothing has run yet
        callbacks[0]()                                # the commit happens now
        doc.refresh_from_db()
        self.assertEqual((doc.status, doc.chunk_count), ("ready", 3))

    def test_a_dead_broker_never_becomes_a_500(self):
        self.login()
        with mock.patch.object(services.ingest_document, "delay",
                               side_effect=OperationalError("no broker")):
            with self.captureOnCommitCallbacks(execute=True):
                reply = self.client.post("/api/v1/documents",
                                         {"filename": "report.pdf"})
        self.assertEqual(reply.status_code, 202)
        doc = Document.objects.get(public_id=reply.data["id"])
        self.assertEqual(doc.status, "failed")
        self.assertIn("temporarily unavailable", doc.error)

    def test_the_api_exposes_progress_and_errors(self):
        self.login()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post("/api/v1/documents", {"filename": "corrupt.pdf"})
        page = self.client.get("/api/v1/documents").json()["results"]
        self.assertEqual(page[0]["status"], "failed")
        self.assertEqual(page[0]["error"], "The file could not be read.")

@override_settings(**FAST)
class ScheduledJobTests(CeleryTestMixin, TestCase):
    def age(self, queryset, **delta):
        field = "deleted_at" if "days" in delta else "created_at"
        queryset.update(**{field: timezone.now() - timedelta(**delta)})

    def test_old_idempotency_keys_are_purged(self):
        for name in ("old", "fresh"):
            IdempotencyKey.objects.create(user=self.ada, key=name,
                                          request_hash="x")
        self.age(IdempotencyKey.objects.filter(key="old"), hours=25)
        self.assertEqual(tasks.purge_idempotency_keys.delay().get(), 1)
        keys = IdempotencyKey.objects.values_list("key", flat=True)
        self.assertEqual(list(keys), ["fresh"])

    def test_conversations_deleted_long_ago_disappear_with_their_messages(self):
        old = Conversation.objects.create(user=self.ada, title="old")
        new = Conversation.objects.create(user=self.ada, title="new")
        services.add_message(old, "user", "hello")
        self.age(Conversation.objects.filter(pk=old.pk), days=31)
        self.age(Conversation.objects.filter(pk=new.pk), days=5)
        self.assertEqual(tasks.purge_deleted_conversations.delay().get(), 1)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 0)         # cascaded

    def test_documents_stuck_in_processing_are_failed(self):
        stuck, busy = self.make_doc("a.pdf"), self.make_doc("b.pdf")
        self.age(Document.objects.filter(pk=stuck.pk), minutes=45)
        self.assertEqual(tasks.fail_stuck_documents.delay().get(), 1)
        stuck.refresh_from_db(); busy.refresh_from_db()
        self.assertEqual((stuck.status, busy.status), ("failed", "processing"))

    def test_the_usage_report_sums_yesterday_per_user(self):
        UsageRecord.objects.create(user=self.ada, input_tokens=100,
                                   output_tokens=50)
        self.age(UsageRecord.objects.all(), hours=24)
        report = tasks.daily_usage_report.delay().get()
        self.assertEqual((report["users"], report["tokens"]), (1, 150))

    def test_every_beat_entry_points_at_a_real_task(self):
        celery_app.loader.import_default_modules()
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            self.assertIn(entry["task"], celery_app.tasks, name)

    def test_ingestion_has_its_own_queue(self):
        route = celery_app.amqp.router.route({}, "chat.tasks.ingest_document")
        self.assertEqual(route["queue"].name, "ingest")
