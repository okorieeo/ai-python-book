import io
from unittest import mock

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from attachments import services, tasks
from attachments.errors import MediaRejected, ProviderConfigError, ProviderUnavailable
from attachments.models import Attachment
from attachments.providers import FakeTranscriber
from attachments.testing import audio_bytes, jpeg, make_message, make_user
from attachments.tests_pdf import text_pdf_bytes

URL = "/api/v1/attachments/"


def upload(client, data: bytes, name="file.bin", url=URL, **extra):
    return client.post(url, {"file": SimpleUploadedFile(name, data), **extra}, format="multipart")


class UploadPipelineTests(APITestCase):
    def setUp(self):
        self.user, self.other = make_user(), make_user("bo@example.com")
        self.client.force_authenticate(self.user)

    def run_upload(self, data, name="file.bin"):
        with self.captureOnCommitCallbacks(execute=True):  # runs the worker task once the row is committed
            response = upload(self.client, data, name)
        return response

    def test_a_picture_is_cleaned_stored_and_the_original_is_deleted(self):
        response = self.run_upload(jpeg(size=(4000, 3000)), "holiday.jpg")
        self.assertEqual(response.status_code, 202)
        attachment = Attachment.objects.get()
        self.assertEqual((attachment.kind, attachment.status), ("image", "ready"))
        self.assertLessEqual(max(attachment.width, attachment.height), 1568)
        self.assertTrue(attachment.processed)
        self.assertFalse(attachment.original)  # the raw file, with its metadata, is gone
        self.assertEqual(attachment.display_name, "holiday.jpg")

    def test_the_status_endpoint_shows_progress_without_private_data(self):
        self.run_upload(jpeg(), "a.jpg")
        attachment = Attachment.objects.get()
        data = self.client.get(f"{URL}{attachment.public_id}/").json()
        self.assertEqual(data["status"], "ready")
        self.assertNotIn("transcript", data)
        self.assertNotIn("original", data)

    def test_a_pdf_is_kept_because_the_model_reads_that_file(self):
        self.run_upload(text_pdf_bytes(3), "report.pdf")
        attachment = Attachment.objects.get()
        self.assertEqual((attachment.status, attachment.page_count), ("ready", 3))
        self.assertTrue(attachment.processed)

    def test_a_voice_recording_becomes_a_transcript_and_the_audio_is_deleted(self):
        fake = FakeTranscriber("buy milk and call the bank")
        with mock.patch.object(tasks, "get_transcriber", return_value=fake):
            self.run_upload(audio_bytes(), "memo.m4a")
        attachment = Attachment.objects.get()
        self.assertEqual((attachment.status, attachment.transcript), ("ready", "buy milk and call the bank"))
        self.assertFalse(attachment.original)
        self.assertFalse(attachment.processed)
        self.assertAlmostEqual(attachment.duration_seconds, 2.0, delta=0.3)
        self.assertEqual(fake.calls[0]["bytes"] > 1000, True)

    def test_silence_is_rejected_with_a_reason(self):
        with mock.patch.object(tasks, "get_transcriber", return_value=FakeTranscriber("")):
            self.run_upload(audio_bytes(), "silent.m4a")
        attachment = Attachment.objects.get()
        self.assertEqual((attachment.status, attachment.error_code), ("rejected", "no_speech_found"))
        self.assertFalse(attachment.original)

    def test_a_file_pretending_to_be_a_picture_never_reaches_storage(self):
        response = upload(self.client, b"<html><script>alert(1)</script></html>", "cute-cat.jpg")
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json()["code"], "unsupported_type")
        self.assertEqual(Attachment.objects.count(), 0)

    def test_an_iphone_heic_photo_gets_a_helpful_refusal(self):
        response = upload(self.client, b"\0\0\0\x18ftypheic\0\0\0\0" + b"x" * 100, "IMG_0001.HEIC")
        self.assertEqual((response.status_code, response.json()["code"]), (415, "heic_not_supported"))

    @override_settings(MEDIA_LIMITS={"max_image_bytes": 1000, "max_pdf_bytes": 1000, "max_audio_bytes": 1000})
    def test_oversized_files_are_refused_before_decoding(self):
        response = upload(self.client, jpeg(size=(800, 600)), "big.jpg")
        self.assertEqual((response.status_code, response.json()["code"]), (413, "file_too_large"))
        self.assertEqual(Attachment.objects.count(), 0)

    @override_settings(MEDIA_LIMITS={"max_uploads_per_day": 2})
    def test_a_daily_upload_limit_applies_per_user(self):
        for _ in range(2):
            self.assertEqual(upload(self.client, jpeg()).status_code, 202)
        self.assertEqual(upload(self.client, jpeg()).status_code, 429)
        self.client.force_authenticate(self.other)
        self.assertEqual(upload(self.client, jpeg()).status_code, 202)

    @override_settings(MEDIA_LIMITS={"max_stored_bytes_per_user": 3000})
    def test_a_storage_quota_applies(self):
        statuses = [upload(self.client, jpeg(size=(320, 240))).status_code for _ in range(3)]
        self.assertIn(413, statuses)

    def test_a_decompression_bomb_is_rejected_by_the_worker(self):
        from attachments.test_images import png_claiming_size
        self.run_upload(png_claiming_size(40_000, 40_000), "bomb.png")
        attachment = Attachment.objects.get()
        self.assertEqual((attachment.status, attachment.error_code), ("rejected", "image_too_many_pixels"))

    def test_other_peoples_attachments_do_not_exist(self):
        self.run_upload(jpeg())
        attachment = Attachment.objects.get()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f"{URL}{attachment.public_id}/").status_code, 404)
        self.assertEqual(self.client.delete(f"{URL}{attachment.public_id}/").status_code, 404)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(f"{URL}{attachment.public_id}/").status_code, (401, 403))

    def test_deleting_removes_the_row_and_the_files(self):
        self.run_upload(jpeg())
        attachment = Attachment.objects.get()
        name = attachment.processed.name
        self.assertTrue(default_storage.exists(name))
        self.assertEqual(self.client.delete(f"{URL}{attachment.public_id}/").status_code, 204)
        self.assertFalse(default_storage.exists(name))
        self.assertEqual(Attachment.objects.count(), 0)

    def test_the_client_supplied_name_never_decides_where_a_file_is_stored(self):
        self.run_upload(jpeg(), "../../../etc/cron.d/evil")
        attachment = Attachment.objects.get()
        self.assertNotIn("evil", attachment.processed.name)
        self.assertNotIn("..", attachment.processed.name)
        self.assertEqual(attachment.display_name, "evil")

    def test_no_file_field_is_a_clean_400(self):
        self.assertEqual(self.client.post(URL, {}, format="multipart").status_code, 400)


class WorkerBehaviourTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def queued(self, data=None, kind="audio", mime="audio/mp4"):
        from django.core.files.base import ContentFile
        attachment = Attachment(user=self.user, kind=kind, mime=mime, size_bytes=1)
        attachment.original.save("x", ContentFile(data if data is not None else audio_bytes()), save=False)
        attachment.save()
        return attachment

    def test_processing_twice_does_the_work_once(self):
        attachment = self.queued()
        fake = FakeTranscriber("hello")
        self.assertEqual(tasks.process(attachment.pk, fake), "ready")
        self.assertEqual(tasks.process(attachment.pk, fake), "already-finished")
        self.assertEqual(len(fake.calls), 1)

    def test_a_provider_outage_leaves_the_attachment_unfinished_for_a_retry(self):
        attachment = self.queued()
        with self.assertRaises(ProviderUnavailable):
            tasks.process(attachment.pk, FakeTranscriber(error=ProviderUnavailable("503")))
        attachment.refresh_from_db()
        self.assertEqual(attachment.status, "processing")
        self.assertTrue(attachment.original)  # still there, so the retry has something to work with

    def test_after_the_last_retry_the_attachment_is_marked_failed(self):
        attachment = self.queued()
        with mock.patch.object(tasks, "process", side_effect=ProviderUnavailable("down")):
            result = tasks.process_attachment.apply(args=[attachment.pk], retries=4).get()  # already tried 4 times
        attachment.refresh_from_db()
        self.assertEqual((result, attachment.status, attachment.error_code), ("failed", "failed", "provider_unavailable"))

    def test_while_retries_remain_the_task_asks_to_be_run_again_later(self):
        from celery.exceptions import Retry
        attachment = self.queued()
        with mock.patch.object(tasks, "process", side_effect=ProviderUnavailable("down")):
            with self.assertRaises(Retry):
                tasks.process_attachment.apply(args=[attachment.pk], retries=0)
        attachment.refresh_from_db()
        self.assertNotEqual(attachment.status, "failed")

    def test_the_task_is_configured_to_retry_a_bounded_number_of_times(self):
        self.assertEqual(tasks.process_attachment.max_retries, 4)
        self.assertTrue(tasks.process_attachment.acks_late)

    def test_a_misconfigured_provider_fails_without_blaming_the_file(self):
        attachment = self.queued()
        tasks.process(attachment.pk, FakeTranscriber(error=ProviderConfigError("bad key")))
        attachment.refresh_from_db()
        self.assertEqual((attachment.status, attachment.error_code), ("failed", "provider_config"))

    def test_a_bug_in_our_code_is_recorded_without_the_users_data(self):
        attachment = self.queued()
        with self.assertLogs("attachments.tasks", level="ERROR") as logs:
            tasks.process(attachment.pk, FakeTranscriber(error=RuntimeError("secret user words")))
        attachment.refresh_from_db()
        self.assertEqual((attachment.status, attachment.error_code), ("failed", "internal_error"))
        self.assertFalse(attachment.original)  # nothing private is left lying around
        self.assertNotIn("secret user words", " ".join(logs.output).split("Traceback")[0])

    def test_a_missing_row_is_ignored(self):
        self.assertEqual(tasks.process(999_999), "missing")


class AttachToMessageTests(TestCase):
    def setUp(self):
        self.user, self.other = make_user(), make_user("bo@example.com")
        self.message = make_message(self.user, role="user", content="look")

    def ready(self, user=None):
        from attachments.testing import ready_attachment
        return ready_attachment(user or self.user, "image", data=jpeg(), mime="image/jpeg")

    def test_ready_attachments_are_linked(self):
        a, b = self.ready(), self.ready()
        services.attach_to_message(user=self.user, message=self.message, public_ids=[a.public_id, b.public_id])
        self.assertEqual(self.message.attachments.count(), 2)

    def test_attachments_that_are_not_ready_cannot_be_sent(self):
        a = self.ready(); Attachment.objects.filter(pk=a.pk).update(status="processing")
        with self.assertRaises(MediaRejected) as ctx:
            services.attach_to_message(user=self.user, message=self.message, public_ids=[a.public_id])
        self.assertEqual(ctx.exception.code, "attachment_not_ready")

    def test_someone_elses_attachment_looks_like_a_missing_one(self):
        theirs = self.ready(self.other)
        with self.assertRaises(MediaRejected) as ctx:
            services.attach_to_message(user=self.user, message=self.message, public_ids=[theirs.public_id])
        self.assertEqual(ctx.exception.code, "attachment_not_found")

    def test_an_attachment_cannot_be_used_twice(self):
        a = self.ready()
        services.attach_to_message(user=self.user, message=self.message, public_ids=[a.public_id])
        with self.assertRaises(MediaRejected):
            services.attach_to_message(user=self.user, message=make_message(self.user, "user"), public_ids=[a.public_id])

    @override_settings(MEDIA_LIMITS={"max_attachments_per_message": 2})
    def test_there_is_a_cap_per_message(self):
        ids = [self.ready().public_id for _ in range(3)]
        with self.assertRaises(MediaRejected) as ctx:
            services.attach_to_message(user=self.user, message=self.message, public_ids=ids)
        self.assertEqual(ctx.exception.code, "too_many_attachments")

    def test_someone_elses_message_does_not_exist(self):
        from chat.models import Message
        with self.assertRaises(Message.DoesNotExist):
            services.attach_to_message(user=self.other, message=self.message, public_ids=[])
