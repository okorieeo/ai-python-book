import os
import re

from django.conf import settings
from rest_framework import exceptions, status

# The first bytes of a file say what it really is, whatever its name claims.
SIGNATURES = [
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
]


class FileTooLarge(exceptions.APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_code = "file_too_large"
    default_detail = "The file is larger than the allowed size."


class UnsupportedFile(exceptions.APIException):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_code = "unsupported_file_type"
    default_detail = "This type of file is not accepted."


class QuotaExceeded(exceptions.APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "storage_quota_exceeded"
    default_detail = "You have used all of your storage."


def sniff(head: bytes):
    """Return (content_type, extension) judged from the content, or None."""
    for magic, content_type, ext in SIGNATURES:
        if head.startswith(magic):
            return content_type, ext
    try:  # plain text: valid UTF-8 and no NUL bytes
        head.decode("utf-8", errors="strict")
        if b"\x00" not in head:
            return "text/plain", ".txt"
    except UnicodeDecodeError:
        pass
    return None


def check_size(size: int):
    if size <= 0:
        raise exceptions.ValidationError({"file": ["The file is empty."]})
    if size > settings.UPLOAD_MAX_BYTES:
        raise FileTooLarge()


def clean_filename(name: str) -> str:
    """A safe display name. It is never used to build a path on disk."""
    name = os.path.basename((name or "").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip(" .")
    return name[:200] or "untitled"
