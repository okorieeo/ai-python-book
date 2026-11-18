from django.apps import AppConfig


class PrivacyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "privacy"

    def ready(self):
        from . import erasers  # noqa: F401  (registers every eraser at startup)
