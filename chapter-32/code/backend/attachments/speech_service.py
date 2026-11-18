import hashlib
import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from chat.models import Message

from .audio import probe_audio, to_speech_wav
from .errors import MediaRejected
from .limits import get_limits
from .providers import Speaker, Transcriber
from .sniff import sniff
from .speech_text import split_for_speech, to_speakable


def dictate(*, upload, transcriber: Transcriber, language: str | None = None) -> str:
    """Short voice note in, text out, right now. The audio is never stored: it only exists in a temp folder
    for the few seconds this takes, and the folder is removed even on failure."""
    limits = get_limits()
    data = upload.read(limits.max_audio_bytes + 1)
    if len(data) > limits.max_audio_bytes:
        raise MediaRejected("file_too_large", "The recording is too large.")
    found = sniff(data[:32])
    if found is None or found.kind != "audio":
        raise MediaRejected("unsupported_type", "This is not an audio recording.")

    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp, "in"), Path(tmp, "out.wav")
        src.write_bytes(data)
        probe_audio(src, max_seconds=limits.max_dictation_seconds)
        to_speech_wav(src, dst, max_seconds=limits.max_dictation_seconds)
        text = transcriber.transcribe(dst.read_bytes(), language=language).text
    if not text:
        raise MediaRejected("no_speech_found", "No speech was found in the recording.")
    return text


def speech_parts(message: Message) -> list[str]:
    return split_for_speech(to_speakable(message.content))


def speak_message(*, user, message_id, part: int, speaker: Speaker, model: str, voice: str, audio_format: str = "mp3"):
    """Audio for one part of an assistant message. Identical text is only ever synthesised once: the second
    request, from this or any other user, is a file read. Returns (audio_bytes, number_of_parts)."""
    message = Message.objects.select_related("conversation").get(
        public_id=message_id, conversation__user=user, role="assistant"  # owner-scoped, like everything else
    )
    parts = speech_parts(message)
    if not parts:
        raise MediaRejected("nothing_to_say", "There is no text to read.")
    if not 0 <= part < len(parts):
        raise MediaRejected("bad_part", "That part does not exist.")

    text = parts[part]
    key = hashlib.sha256(f"{model}|{voice}|{audio_format}|{text}".encode()).hexdigest()
    path = f"speech-cache/{key}.{audio_format}"
    if default_storage.exists(path):
        with default_storage.open(path) as cached:
            return cached.read(), len(parts)

    audio = speaker.synthesize(text, voice=voice, audio_format=audio_format)
    default_storage.save(path, ContentFile(audio))
    return audio, len(parts)
