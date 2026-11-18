import hashlib
import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import MediaRejected
from .limits import MediaLimits, get_limits
from .vision_math import count_image_tokens, resized_size


@dataclass(frozen=True)
class NormalizedImage:
    data: bytes
    mime: str
    width: int
    height: int
    original_width: int
    original_height: int
    sha256: str
    resized: bool
    visual_tokens: int


def _has_alpha(img: Image.Image) -> bool:
    return "A" in img.getbands() or (img.mode == "P" and "transparency" in img.info)


def normalize_image(data: bytes, limits: MediaLimits | None = None) -> NormalizedImage:
    """Turn an untrusted picture into a small, clean, predictable one.

    - refuses pictures whose DECODED size would exhaust memory (a 30 KB file can claim 40000 x 40000 pixels)
    - applies the camera's rotation, then removes ALL metadata (GPS position, camera serial, timestamps)
    - keeps only the first frame of animations
    - resizes to what the model can actually use, which also caps the token cost
    - re-encodes: JPEG, or PNG when there is transparency
    """
    limits = limits or get_limits()
    try:
        # A decompression-bomb WARNING from Pillow becomes an error here, so it can never slip through.
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(data))
            original_width, original_height = img.size  # read from the header: nothing is decoded yet
            if original_width * original_height > limits.max_image_pixels:
                raise MediaRejected("image_too_many_pixels", "The picture has too many pixels.")

            tier = limits.tier
            if img.format == "JPEG":
                # Let the decoder shrink the picture while it reads. Far less memory for big photos.
                img.draft("RGB", (tier.max_edge * 2, tier.max_edge * 2))
            if getattr(img, "n_frames", 1) > 1:
                img.seek(0)
            img.load()
    except MediaRejected:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise MediaRejected("image_too_many_pixels", "The picture has too many pixels.") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise MediaRejected("unreadable_image", "The picture could not be read.") from None

    img = ImageOps.exif_transpose(img)  # bake the camera rotation into the pixels
    alpha = _has_alpha(img)
    img = img.convert("RGBA" if alpha else "RGB")

    target = resized_size(*img.size, tier=tier) if img.size[0] != 0 else img.size
    # `draft` may already have shrunk a JPEG below the original size; never scale UP.
    if img.size[0] * img.size[1] > target[0] * target[1] or max(img.size) > tier.max_edge:
        img = img.resize(target, Image.Resampling.LANCZOS)

    # A brand-new image object from raw pixels carries no metadata at all, whatever the source had.
    clean = Image.frombytes(img.mode, img.size, img.tobytes())
    out, mime = _encode(clean, alpha, limits.max_output_image_bytes)

    return NormalizedImage(
        data=out,
        mime=mime,
        width=clean.size[0],
        height=clean.size[1],
        original_width=original_width,
        original_height=original_height,
        sha256=hashlib.sha256(out).hexdigest(),
        resized=clean.size != (original_width, original_height),
        visual_tokens=count_image_tokens(*clean.size),
    )


def _encode(img: Image.Image, alpha: bool, max_bytes: int) -> tuple[bytes, str]:
    """Encode, lowering JPEG quality and then the size until the result fits the byte budget."""
    for shrink in (1.0, 0.85, 0.7, 0.55):
        candidate = img if shrink == 1.0 else img.resize(
            (max(1, int(img.size[0] * shrink)), max(1, int(img.size[1] * shrink))), Image.Resampling.LANCZOS
        )
        qualities = (None,) if alpha else (85, 75, 65, 50)
        for quality in qualities:
            buffer = io.BytesIO()
            if alpha:
                candidate.save(buffer, format="PNG", optimize=True)
            else:
                candidate.save(buffer, format="JPEG", quality=quality, optimize=True)
            if buffer.tell() <= max_bytes:
                return buffer.getvalue(), "image/png" if alpha else "image/jpeg"
    raise MediaRejected("image_too_complex", "The picture is too detailed to shrink to an acceptable size.")
