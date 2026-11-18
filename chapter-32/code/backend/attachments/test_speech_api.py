import tempfile
from unittest import mock

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from attachments import tasks, views
from attachments.errors import ProviderUnavailable
from attachments.models import Attachment
from attachments.providers import FakeSpeaker, FakeTranscriber
from attachments.testing import audio_bytes, jpeg, make_message, make_user

DICTATE = "/api/v1/dictation/"


def stored_files() -> list[str]:
    found = []
    stack = [""]
    while stack:
        directory = stack.pop()
        dirs, files = default_storage.listdir(directory)
        found += [f"{directory}/{f}".lstrip("/") for f in files]
        stack += [f"{directory}/{d}".lstrip("/") for d in dirs]
    return found


class DictationTests(APITestCase):
    def setUp(self):
        # every test gets its own empty storage folder, so cached audio from one test cannot leak into another
        tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=tmp))
        self.user = make_user()
        self.client.force_authenticate(self.user)

    def post(self, data: bytes, name="note.m4a", **extra):
        return self.client.post(DICTATE, {"file": SimpleUploadedFile(name, data), **extra}, format="multipart")

    def test_a_voice_note_comes_back_as_text(self):
        fake = FakeTranscriber("remind me to water the plants")
        with mock.patch.object(tasks, "get_transcriber", return_value=fake):
            response = self.post(audio_bytes(), language="en")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"text": "remind me to water the plants"})
        self.assertEqual(fake.calls[0]["language"], "en")

    def test_the_audio_is_never_stored_and_no_row_is_created(self):
        before = stored_files()
        with mock.patch.object(tasks, "get_transcriber", return_value=FakeTranscriber("hi")):
            self.post(audio_bytes())
        self.assertEqual(stored_files(), before)
        self.assertEqual(Attachment.objects.count(), 0)

    @override_settings(MEDIA_LIMITS={"max_dictation_seconds": 1})
    def test_a_recording_longer_than_the_dictation_limit_is_refused(self):
        with mock.patch.object(tasks, "get_transcriber", return_value=FakeTranscriber("hi")) as patched:
            response = self.post(audio_bytes(seconds=3))
        self.assertEqual((response.status_code, response.json()["code"]), (422, "audio_too_long"))
        self.assertEqual(patched.return_value.calls, [])  # refused before any money was spent

    def test_a_picture_is_not_a_recording(self):
        response = self.post(jpeg(), "note.m4a")
        self.assertEqual((response.status_code, response.json()["code"]), (415, "unsupported_type"))

    def test_an_outage_is_a_clear_503_the_app_can_retry(self):
        fake = FakeTranscriber(error=ProviderUnavailable("down"))
        with mock.patch.object(tasks, "get_transcriber", return_value=fake):
            response = self.post(audio_bytes())
        self.assertEqual((response.status_code, response.json()["code"]), (503, "speech_unavailable"))

    def test_silence_is_reported_not_returned_as_empty_text(self):
        with mock.patch.object(tasks, "get_transcriber", return_value=FakeTranscriber("")):
            response = self.post(audio_bytes())
        self.assertEqual((response.status_code, response.json()["code"]), (422, "no_speech_found"))

    def test_anonymous_requests_are_refused(self):
        self.client.force_authenticate(None)
        self.assertIn(self.post(audio_bytes()).status_code, (401, 403))


class SpeakTests(APITestCase):
    def setUp(self):
        # every test gets its own empty storage folder, so cached audio from one test cannot leak into another
        tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=tmp))
        self.user, self.other = make_user(), make_user("bo@example.com")
        self.client.force_authenticate(self.user)
        self.message = make_message(self.user, "assistant", "## Plan\n\n- **Walk** the dog\n- Read [this](https://example.com/x)")

    def url(self, message=None):
        return f"/api/v1/messages/{(message or self.message).public_id}/speech/"

    def patched(self, speaker):
        return mock.patch.object(views, "get_speaker", return_value=speaker)

    def test_the_reply_is_read_aloud_without_markdown_noise(self):
        speaker = FakeSpeaker(b"ID3audio")
        with self.patched(speaker):
            response = self.client.get(self.url())
        self.assertEqual((response.status_code, response["Content-Type"], response.content), (200, "audio/mpeg", b"ID3audio"))
        self.assertEqual(response["X-Speech-Parts"], "1")
        self.assertEqual(speaker.calls[0]["text"], "Plan\n\nWalk the dog\nRead this")
        self.assertEqual(speaker.calls[0]["voice"], "voice-1")

    def test_the_same_text_is_synthesised_only_once(self):
        speaker = FakeSpeaker()
        with self.patched(speaker):
            self.client.get(self.url())
            second = self.client.get(self.url())
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(speaker.calls), 1)

    def test_a_long_reply_is_served_in_parts(self):
        long = make_message(self.user, "assistant", " ".join(f"Sentence number {i} is here." for i in range(400)))
        speaker = FakeSpeaker()
        with self.patched(speaker):
            first = self.client.get(self.url(long))
            parts = int(first["X-Speech-Parts"])
            last = self.client.get(self.url(long) + f"?part={parts - 1}")
        self.assertGreater(parts, 1)
        self.assertEqual(last.status_code, 200)
        self.assertTrue(all(len(c["text"]) <= 4000 for c in speaker.calls))

    def test_other_peoples_messages_and_your_own_prompts_cannot_be_read_aloud(self):
        mine = make_message(self.user, "user", "my own question")
        with self.patched(FakeSpeaker()):
            self.assertEqual(self.client.get(self.url(mine)).status_code, 404)
            self.client.force_authenticate(self.other)
            self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_the_part_count_is_available_without_spending_money(self):
        speaker = FakeSpeaker()
        with self.patched(speaker):
            response = self.client.get(self.url() + "?info=1")
        self.assertEqual(response.json(), {"parts": 1})
        self.assertEqual(speaker.calls, [])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url() + "?info=1").status_code, 404)

    def test_bad_part_numbers_are_refused(self):
        with self.patched(FakeSpeaker()):
            self.assertEqual(self.client.get(self.url() + "?part=7").json()["code"], "bad_part")
            self.assertEqual(self.client.get(self.url() + "?part=abc").status_code, 400)

    def test_an_outage_is_a_clear_503(self):
        with self.patched(FakeSpeaker(error=ProviderUnavailable("down"))):
            response = self.client.get(self.url())
        self.assertEqual((response.status_code, response.json()["code"]), (503, "speech_unavailable"))
        self.assertEqual(default_storage.exists("speech-cache"), False)  # a failure is never cached
