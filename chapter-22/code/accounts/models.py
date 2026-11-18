import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        MEMBER = "member"
        SUPPORT = "support"
        ADMIN = "admin"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    role = models.CharField(max_length=20, choices=Role.choices,
                            default=Role.MEMBER, db_index=True)
