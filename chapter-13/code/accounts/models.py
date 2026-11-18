import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(
            password
        )  # password=None stores an unusable password
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra):
        extra.update(
            is_staff=True,
            is_superuser=True,
            role="admin",
            email_verified=True,
        )
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        MEMBER = "member"
        ADMIN = "admin"

    public_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False
    )
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=200)
    role = models.CharField(max_length=10, choices=Role, default=Role.MEMBER)
    email_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "users"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=["member", "admin"]),
                name="users_role_valid",
            )
        ]

    def __str__(self):
        return self.email


class SocialAccount(models.Model):
    """Links a user to an identity at an OAuth provider, such as Google."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="social"
    )
    provider = models.CharField(max_length=20)
    uid = models.CharField(max_length=255)  # the provider's stable user id
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "social_accounts"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "uid"], name="social_provider_uid_key"
            )
        ]


class Farm(models.Model):
    public_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False
    )
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "farms"


class FarmMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner"
        MANAGER = "manager"
        WORKER = "worker"

    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="members"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="farms"
    )
    role = models.CharField(max_length=10, choices=Role)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "farm_members"
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "user"], name="farm_member_once"
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=["owner", "manager", "worker"]),
                name="farm_member_role_valid",
            ),
        ]
