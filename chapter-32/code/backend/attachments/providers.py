"""Speech providers behind two tiny interfaces. Model names and voices are CONFIGURATION, never code:
vendors retire models on a schedule (see section 32.2), and a retired name must be a settings change."""
import io
from dataclasses import dataclass
from typing import Protocol

import openai
from openai import OpenAI

from .errors import MediaRejected, ProviderConfigError, ProviderUnavailable


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None = None


class Transcriber(Protocol):
    def transcribe(self, wav: bytes, *, language: str | None = None) -> Transcript: ...


class Speaker(Protocol):
    def synthesize(self, text: str, *, voice: str, audio_format: str = "mp3") -> bytes: ...


def _translate(exc: Exception):
    """Sort a provider failure into the three kinds our code knows how to handle."""
    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError)):
        return ProviderUnavailable(type(exc).__name__)
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code >= 500 or exc.status_code in (408, 409, 429):
            return ProviderUnavailable(f"status {exc.status_code}")
        if exc.status_code in (401, 403, 404):  # wrong key, no access, or a model name that no longer exists
            return ProviderConfigError(f"provider answered {exc.status_code}: check the key and the model name")
        return MediaRejected("provider_rejected", "The speech service could not use this audio.")
    return exc


def make_client(*, api_key: str, base_url: str | None = None, timeout: float = 30.0) -> OpenAI:
    """max_retries=0 on purpose: Celery (or the caller) retries. Retry in exactly one place."""
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)


class OpenAICompatibleTranscriber:
    """Works with any server that speaks the same /audio/transcriptions protocol, hosted or self-hosted."""

    def __init__(self, client: OpenAI, model: str):
        self.client, self.model = client, model

    def transcribe(self, wav: bytes, *, language: str | None = None) -> Transcript:
        params = {"model": self.model, "file": ("audio.wav", io.BytesIO(wav), "audio/wav")}
        if language:
            params["language"] = language  # a known language improves accuracy and speed
        try:
            result = self.client.audio.transcriptions.create(**params)
        except Exception as exc:
            raise _translate(exc) from exc
        return Transcript(text=(result.text or "").strip(), language=language)


class OpenAICompatibleSpeaker:
    def __init__(self, client: OpenAI, model: str):
        self.client, self.model = client, model

    def synthesize(self, text: str, *, voice: str, audio_format: str = "mp3") -> bytes:
        try:
            response = self.client.audio.speech.create(
                model=self.model, voice=voice, input=text, response_format=audio_format
            )
        except Exception as exc:
            raise _translate(exc) from exc
        return response.content


class FakeTranscriber:
    """For tests and for development without a key. Records what it was asked."""

    def __init__(self, text: str = "hello from the fake transcriber", error: Exception | None = None):
        self.text, self.error, self.calls = text, error, []

    def transcribe(self, wav: bytes, *, language: str | None = None) -> Transcript:
        self.calls.append({"bytes": len(wav), "language": language})
        if self.error:
            raise self.error
        return Transcript(self.text, language)


class FakeSpeaker:
    def __init__(self, audio: bytes = b"ID3fake-mp3-bytes", error: Exception | None = None):
        self.audio, self.error, self.calls = audio, error, []

    def synthesize(self, text: str, *, voice: str, audio_format: str = "mp3") -> bytes:
        self.calls.append({"text": text, "voice": voice, "format": audio_format})
        if self.error:
            raise self.error
        return self.audio
