from dataclasses import dataclass, replace

from django.conf import settings

from .vision_math import HIGH_RES, STANDARD, Tier


@dataclass(frozen=True)
class MediaLimits:
    """Every number that protects the server and the bill, in one place. Override in settings."""

    max_image_bytes: int = 10 * 1024 * 1024
    max_pdf_bytes: int = 20 * 1024 * 1024
    max_audio_bytes: int = 20 * 1024 * 1024
    max_image_pixels: int = 50_000_000  # width x height of the DECODED image; about 200 MB as RGBA
    max_output_image_bytes: int = 4 * 1024 * 1024  # base64 grows it by a third, and the API has its own cap
    max_pdf_pages: int = 100
    max_audio_seconds: int = 600
    max_dictation_seconds: int = 60
    max_attachments_per_message: int = 5
    max_uploads_per_day: int = 50
    max_stored_bytes_per_user: int = 200 * 1024 * 1024
    vision_tier: str = "standard"  # "standard" or "high_res": match the model you call

    @property
    def tier(self) -> Tier:
        return HIGH_RES if self.vision_tier == "high_res" else STANDARD


def get_limits() -> MediaLimits:
    overrides = getattr(settings, "MEDIA_LIMITS", {})
    return replace(MediaLimits(), **overrides)
