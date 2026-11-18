import json

import httpx
from django.test import SimpleTestCase
from openai import OpenAI

from attachments.errors import MediaRejected, ProviderConfigError, ProviderUnavailable
from attachments.providers import OpenAICompatibleSpeaker, OpenAICompatibleTranscriber, make_client


def client_with(handler) -> OpenAI:
    return OpenAI(api_key="k", base_url="https://speech.test/v1", max_retries=0,
                  http_client=httpx.Client(transport=httpx.MockTransport(handler)))


class TranscriberTests(SimpleTestCase):
    def test_request_has_the_model_the_file_and_the_language(self):
        seen = {}

        def handler(request: httpx.Request):
            seen["path"], seen["body"] = request.url.path, request.read()
            return httpx.Response(200, json={"text": "  hello world  "})

        result = OpenAICompatibleTranscriber(client_with(handler), model="my-model").transcribe(b"RIFFwavbytes", language="en")
        self.assertEqual(seen["path"], "/v1/audio/transcriptions")
        for needle in (b'name="model"', b"my-model", b'filename="audio.wav"', b'name="language"', b"RIFFwavbytes"):
            self.assertIn(needle, seen["body"])
        self.assertEqual(result.text, "hello world")

    def test_no_language_means_no_language_field(self):
        seen = {}

        def handler(request):
            seen["body"] = request.read()
            return httpx.Response(200, json={"text": "x"})

        OpenAICompatibleTranscriber(client_with(handler), model="m").transcribe(b"abc")
        self.assertNotIn(b'name="language"', seen["body"])

    def test_failures_are_sorted_into_retry_fix_or_reject(self):
        def failing(status):
            return lambda request: httpx.Response(status, json={"error": {"message": "nope"}})

        transcribe = lambda handler: OpenAICompatibleTranscriber(client_with(handler), model="m").transcribe(b"abc")  # noqa: E731
        for status in (429, 500, 502, 503):
            with self.assertRaises(ProviderUnavailable, msg=str(status)):
                transcribe(failing(status))
        for status in (401, 403, 404):  # wrong key or a model name that has been retired
            with self.assertRaises(ProviderConfigError, msg=str(status)):
                transcribe(failing(status))
        with self.assertRaises(MediaRejected):
            transcribe(failing(400))

    def test_timeouts_and_dropped_connections_are_retryable(self):
        def timeout(request):
            raise httpx.ReadTimeout("slow", request=request)

        def refused(request):
            raise httpx.ConnectError("refused", request=request)

        for handler in (timeout, refused):
            with self.assertRaises(ProviderUnavailable):
                OpenAICompatibleTranscriber(client_with(handler), model="m").transcribe(b"abc")

    def test_the_client_does_not_retry_by_itself(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(500, json={})

        with self.assertRaises(ProviderUnavailable):
            OpenAICompatibleTranscriber(client_with(handler), model="m").transcribe(b"abc")
        self.assertEqual(len(calls), 1)  # retrying is Celery's job: one place, not two
        self.assertEqual(make_client(api_key="k").max_retries, 0)


class SpeakerTests(SimpleTestCase):
    def test_request_carries_model_voice_text_and_format_and_returns_the_bytes(self):
        seen = {}

        def handler(request: httpx.Request):
            seen["path"], seen["json"] = request.url.path, json.loads(request.read())
            return httpx.Response(200, content=b"ID3audio", headers={"content-type": "audio/mpeg"})

        audio = OpenAICompatibleSpeaker(client_with(handler), model="tts-x").synthesize("Hello there", voice="v9", audio_format="mp3")
        self.assertEqual(seen["path"], "/v1/audio/speech")
        self.assertEqual(seen["json"], {"model": "tts-x", "voice": "v9", "input": "Hello there", "response_format": "mp3"})
        self.assertEqual(audio, b"ID3audio")

    def test_a_retired_model_is_a_configuration_error_not_a_user_error(self):
        handler = lambda request: httpx.Response(404, json={"error": {"message": "model not found"}})  # noqa: E731
        with self.assertRaises(ProviderConfigError):
            OpenAICompatibleSpeaker(client_with(handler), model="retired").synthesize("hi", voice="v")
