from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from chat.models import Message

from .errors import MediaRejected
from .limits import get_limits
from .models import Attachment
from .sniff import is_heic, safe_filename, sniff

HEAD_BYTES = 32


def create_attachment(*, user, upload, enqueue=None) -> Attachment:
    """Accept an upload: check it, store it privately, and hand it to a worker. Nothing is decoded here."""
    from .tasks import process_attachment  # imported late: tasks imports this module's siblings

    limits = get_limits()
    kind_limits = {"image": limits.max_image_bytes, "document": limits.max_pdf_bytes, "audio": limits.max_audio_bytes}
    biggest = max(kind_limits.values())

    # Read at most one byte more than the largest allowed size: a 10 GB upload never fills memory.
    data = upload.read(biggest + 1)
    if len(data) > biggest:
        raise MediaRejected("file_too_large", "The file is too large.")

    found = sniff(data[:HEAD_BYTES])
    if found is None:
        if is_heic(data[:HEAD_BYTES]):
            raise MediaRejected("heic_not_supported", "This photo is in HEIC format. Please share it as a JPEG.")
        raise MediaRejected("unsupported_type", "This type of file is not supported.")
    if len(data) > kind_limits[found.kind]:
        raise MediaRejected("file_too_large", "The file is too large.")

    # Per-user limits: one account cannot fill the disk or the bill.
    since = timezone.now() - timedelta(days=1)
    if Attachment.objects.filter(user=user, created_at__gte=since).count() >= limits.max_uploads_per_day:
        raise MediaRejected("daily_upload_limit", "You have reached today's upload limit.")
    stored = Attachment.objects.filter(user=user).aggregate(total=Sum("size_bytes"))["total"] or 0
    if stored + len(data) > limits.max_stored_bytes_per_user:
        raise MediaRejected("storage_quota_exceeded", "You have used all of your storage.")

    from django.core.files.base import ContentFile

    attachment = Attachment(
        user=user, kind=found.kind, mime=found.mime, size_bytes=len(data),
        display_name=safe_filename(getattr(upload, "name", None)),
    )
    attachment.original.save("ignored", ContentFile(data), save=False)  # the real path is random (see models.py)
    attachment.save()

    # Only after the database row is committed, so a worker can never look for a row that does not exist yet.
    run = enqueue or process_attachment.delay
    transaction.on_commit(lambda: run(attachment.pk))
    return attachment


def attach_to_message(*, user, message: Message, public_ids: list) -> list[Attachment]:
    """Link READY attachments of this user to one of their messages."""
    limits = get_limits()
    if message.conversation.user_id != user.id:
        raise Message.DoesNotExist  # never reveal that the conversation exists
    if len(public_ids) > limits.max_attachments_per_message:
        raise MediaRejected("too_many_attachments", f"At most {limits.max_attachments_per_message} files per message.")

    found = list(Attachment.objects.filter(user=user, public_id__in=public_ids, message__isnull=True))
    if len(found) != len(set(public_ids)):
        raise MediaRejected("attachment_not_found", "One of the files is missing or already used.")
    not_ready = [a for a in found if a.status != Attachment.Status.READY]
    if not_ready:
        raise MediaRejected("attachment_not_ready", "A file is still being processed or could not be used.")
    for attachment in found:
        attachment.message = message
        attachment.save(update_fields=["message", "updated_at"])
    return found
