import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Sniffed:
    kind: str  # "image", "document" or "audio"
    mime: str
    ext: str


def sniff(head: bytes) -> Sniffed | None:
    """Decide what a file REALLY is from its first bytes. The file name and the Content-Type header are
    chosen by the sender, so they are only hints and we never trust them.

    Returns None for anything we do not accept. Accepting fewer types is the safe direction.
    """
    if head.startswith(b"\xff\xd8\xff"):
        return Sniffed("image", "image/jpeg", ".jpg")
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return Sniffed("image", "image/png", ".png")
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return Sniffed("image", "image/gif", ".gif")
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return Sniffed("image", "image/webp", ".webp")
    if head.startswith(b"%PDF-"):
        return Sniffed("document", "application/pdf", ".pdf")

    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return Sniffed("audio", "audio/wav", ".wav")
    if head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return Sniffed("audio", "audio/mpeg", ".mp3")
    if head.startswith(b"OggS"):
        return Sniffed("audio", "audio/ogg", ".ogg")
    if head.startswith(b"fLaC"):
        return Sniffed("audio", "audio/flac", ".flac")
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return Sniffed("audio", "audio/webm", ".webm")
    if head[4:8] == b"ftyp" and not is_heic(head):
        # m4a, mp4, 3gp: all the same container family. It may even hold video, which ffmpeg drops later.
        return Sniffed("audio", "audio/mp4", ".m4a")
    return None


HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"heim", b"heis"}


def is_heic(head: bytes) -> bool:
    """iPhone photos can be HEIC. We recognise it only to give a helpful message instead of "unsupported"."""
    return head[4:8] == b"ftyp" and head[8:12] in HEIC_BRANDS


def safe_filename(name: str | None, fallback: str = "upload") -> str:
    """Keep only a harmless base name for display. We never use it to build a storage path."""
    base = os.path.basename((name or "").replace("\\", "/"))
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip().strip(".")
    return base[:100] or fallback
