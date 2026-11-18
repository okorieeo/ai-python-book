import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    """Minimal custom user. Chapter 13 adds email login, roles and more."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
