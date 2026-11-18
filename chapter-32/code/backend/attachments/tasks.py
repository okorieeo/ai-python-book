import logging

from celery import shared_task
from django.core.files.base import ContentFile

from .audio import probe_audio, to_speech_wav
from .documents import inspect_pdf
from .errors import MediaRejected, ProviderConfigError, ProviderUnavailable
from .images import normalize_image
from .limits import get_limits
from .models import Attachment
from .providers import Transcriber

import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)
FINISHED = (Attachment.Status.READY, Attachment.Status.REJECTED, Attachment.Status.FAILED)


def get_transcriber() -> Transcriber:
    """The one place that decides which provider is used. Replace it in tests; build it from settings in production."""
    from django.conf import settings
    from .providers import OpenAICompatibleTranscriber, make_client

    client = make_client(api_key=settings.SPEECH_API_KEY, base_url=getattr(settings, "SPEECH_BASE_URL", None))
    return OpenAICompatibleTranscriber(client, model=settings.TRANSCRIPTION_MODEL)


def process(attachment_id: int, transcriber: Transcriber | None = None) -> str:
    """Do the work. Safe to run twice: a finished attachment is left alone, and every step overwrites its own result.

    Raises ProviderUnavailable for failures that may pass (the Celery wrapper retries those).
    Everything permanent is recorded on the row and returns normally.
    """
    try:
        attachment = Attachment.objects.get(pk=attachment_id)
    except Attachment.DoesNotExist:
        return "missing"
    if attachment.status in FINISHED:
        return "already-finished"

    Attachment.objects.filter(pk=attachment.pk).update(status=Attachment.Status.PROCESSING)
    limits = get_limits()
    try:
        data = attachment.original.read() if attachment.original else b""
        attachment.original.close()
        if attachment.kind == Attachment.Kind.IMAGE:
            _process_image(attachment, data)
        elif attachment.kind == Attachment.Kind.DOCUMENT:
            _process_pdf(attachment, data)
        else:
            _process_audio(attachment, data, transcriber or get_transcriber(), limits.max_audio_seconds)
    except MediaRejected as exc:
        _finish(attachment, Attachment.Status.REJECTED, exc.code)
        return "rejected"
    except ProviderUnavailable:
        raise  # not finished: the wrapper retries, and `FINISHED` stays false in the meantime
    except ProviderConfigError:
        logger.error("speech provider misconfigured", extra={"attachment": attachment.pk})
        _finish(attachment, Attachment.Status.FAILED, "provider_config")
        return "failed"
    except Exception:
        # A bug of ours. Log the type and the id: never the content, which is the user's private data.
        logger.exception("attachment processing crashed", extra={"attachment": attachment.pk})
        _finish(attachment, Attachment.Status.FAILED, "internal_error")
        return "failed"

    # Privacy by default: once the cleaned copy (or the transcript) exists, the raw original, with its
    # metadata, is deleted. A PDF is the exception because the model reads that very file.
    if attachment.kind != Attachment.Kind.DOCUMENT and attachment.original:
        attachment.original.delete(save=False)
        attachment.original = None
    attachment.status, attachment.error_code = Attachment.Status.READY, ""
    attachment.save()
    return "ready"


def _finish(attachment: Attachment, status: str, code: str) -> None:
    attachment.status, attachment.error_code = status, code
    if status != Attachment.Status.READY and attachment.original:  # nothing usable came out: keep no private data
        attachment.original.delete(save=False)
        attachment.original = None
    attachment.save()


def _process_image(attachment: Attachment, data: bytes) -> None:
    result = normalize_image(data)
    attachment.processed.save("ignored", ContentFile(result.data), save=False)
    attachment.processed_mime, attachment.sha256 = result.mime, result.sha256
    attachment.width, attachment.height, attachment.visual_tokens = result.width, result.height, result.visual_tokens


def _process_pdf(attachment: Attachment, data: bytes) -> None:
    info = inspect_pdf(data)
    attachment.processed = attachment.original  # the model reads the PDF itself, so the same file is used
    attachment.processed_mime = "application/pdf"
    attachment.page_count = info.pages


def _process_audio(attachment: Attachment, data: bytes, transcriber: Transcriber, max_seconds: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:  # removed even if something fails: audio is private
        src, dst = Path(tmp, "in"), Path(tmp, "out.wav")
        src.write_bytes(data)
        info = probe_audio(src, max_seconds=max_seconds)
        to_speech_wav(src, dst, max_seconds=max_seconds)
        transcript = transcriber.transcribe(dst.read_bytes())
    attachment.transcript = transcript.text
    attachment.duration_seconds = info.duration
    if not transcript.text:
        raise MediaRejected("no_speech_found", "No speech was found in the recording.")


@shared_task(bind=True, max_retries=4, acks_late=True)
def process_attachment(self, attachment_id: int):
    try:
        return process(attachment_id)
    except ProviderUnavailable as exc:
        if self.request.retries >= self.max_retries:
            Attachment.objects.filter(pk=attachment_id).update(status=Attachment.Status.FAILED, error_code="provider_unavailable")
            return "failed"
        # exponential backoff with jitter, as in Chapter 25: 5 s, 10 s, 20 s, 40 s, each randomised
        from random import random
        raise self.retry(exc=exc, countdown=(5 * 2 ** self.request.retries) * (0.5 + random() / 2))
