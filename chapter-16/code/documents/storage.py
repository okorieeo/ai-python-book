import hashlib
import uuid

import boto3
from botocore.config import Config
from django.conf import settings
from django.core.files.storage import FileSystemStorage, storages


def get_storage():
    return storages[
        "default"
    ]  # local folder in dev, S3-compatible in production


def is_local(storage) -> bool:
    return isinstance(storage, FileSystemStorage)


def new_key(user, ext: str) -> str:
    """Our own key. The user's filename never becomes part of a path."""
    return f"documents/{user.public_id}/{uuid.uuid4().hex}{ext}"


def sha256_of(chunks) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def s3_client():
    cfg = settings.S3
    return boto3.client(
        "s3",
        endpoint_url=cfg["endpoint_url"],
        region_name=cfg["region_name"],
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
        config=Config(signature_version="s3v4"),
    )
