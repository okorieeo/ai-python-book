import io

from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

MAX_PIXELS = 25_000_000  # 25 megapixels: bigger than any phone photo you need
AVATAR_SIZE = 512


def process_avatar(uploaded) -> bytes:
    """Return a clean 512px WebP. Raises ValidationError for anything else."""
    try:
        image = Image.open(uploaded)
        if image.width * image.height > MAX_PIXELS:  # a "decompression bomb"
            raise ValidationError({"file": ["The image is too large."]})
        image = ImageOps.exif_transpose(image)  # honour the camera's rotation
        image = image.convert("RGB")  # drops transparency tricks
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ):
        raise ValidationError({"file": ["This is not a valid image."]})
    image.thumbnail((AVATAR_SIZE, AVATAR_SIZE))
    out = io.BytesIO()
    image.save(
        out, "WEBP", quality=85
    )  # re-encoding strips EXIF and GPS data
    return out.getvalue()
