import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import MediaRejected
from .limits import MediaLimits, get_limits

# Both tools only read LOCAL files: a crafted file that names a network address or another local file
# inside a playlist is refused, which closes a classic server-side request forgery and file-read trick.
_SAFE_INPUT = ["-protocol_whitelist", "file"]


@dataclass(frozen=True)
class AudioInfo:
    duration: float
    codec: str
    sample_rate: int
    channels: int
    has_video: bool


def _run(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Run a tool with a list of arguments (never a shell string) and a hard time limit."""
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise MediaRejected("audio_processing_timeout", "The audio took too long to process.") from None
    except FileNotFoundError as exc:  # our server is misconfigured, not the user's file
        raise RuntimeError(f"{args[0]} is not installed on this server") from exc


def probe_audio(path: str | Path, limits: MediaLimits | None = None, max_seconds: int | None = None,
                timeout: int = 20) -> AudioInfo:
    limits = limits or get_limits()
    max_seconds = max_seconds or limits.max_audio_seconds
    result = _run(
        ["ffprobe", "-v", "error", *_SAFE_INPUT, "-print_format", "json", "-show_format", "-show_streams", str(path)],
        timeout,
    )
    if result.returncode != 0:
        raise MediaRejected("unreadable_audio", "The audio could not be read.")
    try:
        info = json.loads(result.stdout)
        streams = info.get("streams", [])
        audio = next(s for s in streams if s.get("codec_type") == "audio")
        duration = float(info["format"]["duration"])
    except (ValueError, KeyError, StopIteration):
        raise MediaRejected("unreadable_audio", "The audio has no readable sound track.") from None
    if duration > max_seconds:
        raise MediaRejected("audio_too_long", f"The audio is longer than {max_seconds} seconds.")
    return AudioInfo(
        duration=duration,
        codec=str(audio.get("codec_name", "")),
        sample_rate=int(audio.get("sample_rate", 0) or 0),
        channels=int(audio.get("channels", 0) or 0),
        has_video=any(s.get("codec_type") == "video" for s in streams),
    )


def to_speech_wav(src: str | Path, dst: str | Path, max_seconds: int, timeout: int = 90) -> None:
    """Convert to what speech models like best: mono, 16 kHz, plain WAV. Also drops video and metadata,
    and never writes more than max_seconds, even if the file lied about its length."""
    result = _run(
        [
            "ffmpeg", "-nostdin", "-v", "error", *_SAFE_INPUT, "-i", str(src),
            "-map", "0:a:0", "-vn", "-map_metadata", "-1",
            "-ac", "1", "-ar", "16000", "-t", str(max_seconds),
            "-f", "wav", "-y", str(dst),
        ],
        timeout,
    )
    if result.returncode != 0 or not Path(dst).exists() or Path(dst).stat().st_size < 100:
        raise MediaRejected("unreadable_audio", "The audio could not be converted.")
