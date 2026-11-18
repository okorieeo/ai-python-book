import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Tier:
    """The image limits of a model family. Check the vision page of the Claude docs for your model."""

    name: str
    max_edge: int
    max_tokens: int


STANDARD = Tier("standard", 1568, 1568)
HIGH_RES = Tier("high_res", 2576, 4784)

PATCH = 28  # the model looks at the image in 28 x 28 pixel patches; each patch is one visual token


def count_image_tokens(width: int, height: int) -> int:
    return math.ceil(width / PATCH) * math.ceil(height / PATCH)


def _fits(width: int, height: int, tier: Tier) -> bool:
    # Both the edge limit and the token limit must hold. The edge test uses the size rounded UP to whole patches.
    return (
        math.ceil(width / PATCH) * PATCH <= tier.max_edge
        and math.ceil(height / PATCH) * PATCH <= tier.max_edge
        and count_image_tokens(width, height) <= tier.max_tokens
    )


def resized_size(width: int, height: int, tier: Tier = STANDARD) -> tuple[int, int]:
    """The largest size, at the same aspect ratio, that the model accepts without resizing it further.

    If we resize to this size ourselves, we choose how the picture is shrunk and the model never has to.
    """
    if width < 1 or height < 1:
        raise ValueError("an image needs a positive size")
    if _fits(width, height, tier):
        return width, height
    if height > width:  # work on the long edge; swap, solve, swap back
        h, w = resized_size(height, width, tier)
        return w, h

    ratio = width / height
    low, high = 1, width  # `low` always fits, `high` never does
    while low + 1 < high:
        mid = (low + high) // 2
        if _fits(mid, max(round(mid / ratio), 1), tier):
            low = mid
        else:
            high = mid
    return low, max(round(low / ratio), 1)
