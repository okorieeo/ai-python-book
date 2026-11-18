"""Small helpers shared by the tests of this app."""
import io
import subprocess
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from PIL import Image

from chat.models import Conversation, Message

from .models import Attachment

User = get_user_model()


def make_user(email="ada@example.com"):
    return User.objects.create_user(email=email, password="a-long-test-password")


def make_message(user, role="assistant", content="Hello there."):
    conversation = Conversation.objects.create(user=user, title="Plans")
    return Message.objects.create(conversation=conversation, role=role, content=content)


def jpeg(size=(320, 240), color=(10, 120, 200)) -> bytes:
    buf = io.BytesIO(); Image.new("RGB", size, color).save(buf, "JPEG"); return buf.getvalue()


def audio_bytes(suffix=".m4a", seconds=2.0) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp, f"a{suffix}")
        extra = ["-c:a", "aac"] if suffix == ".m4a" else []
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", *extra, str(path)],
                       check=True, capture_output=True)
        return path.read_bytes()


def ready_attachment(user, kind, *, data=b"", mime="", **fields) -> Attachment:
    """A finished attachment, without running the pipeline."""
    attachment = Attachment(user=user, kind=kind, status=Attachment.Status.READY, mime=mime, processed_mime=mime, **fields)
    if data:
        attachment.processed.save("ignored", ContentFile(data), save=False)
    attachment.save()
    return attachment
