# Chapter 32 — Multimodal and Specialized AI Features: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Providers: Model Names Are Configuration

Before writing any code, a lesson from the real world that decides how the code is shaped. While preparing this chapter we read the documentation inside the OpenAI Python SDK (version 3.46.0). For text-to-speech it lists `tts-1`, `tts-1-hd` and `gpt-4o-mini-tts` as deprecated with a shutdown date of **January 6, 2027**. For transcription it lists several models with shutdown dates of **February 26, 2027**, and a newer transcription model name appears beside them. Vendors announce a replacement, give a date, and expect you to move.

An app that wrote a model name into twenty places, or built its whole speech layer around one vendor’s response shape, now has a deadline and a refactor. An app that kept the model name in an environment variable, and the vendor behind a ten-line interface, has a one-line change and a test run. The same applies to image models, to Claude model names and to voices.

| **Capability** | **In this chapter** | **Other options you can swap in** |
|---|---|---|
| **Understand pictures and PDFs** | Claude through the Messages API (Chapter 29 service layer) | Another multimodal LLM behind the same service interface |
| **Speech to text** | Any server speaking the common `/audio/transcriptions` protocol, hosted or self-hosted | A vendor SDK, or an open-weight model such as Whisper that you run yourself (the plan in your own-model chapters) |
| **Text to speech** | The phone’s built-in voice (free, offline), or a server voice through the same kind of adapter | Any vendor, or an open-weight voice model you host |
| **Read text from a photo** | Claude reads it directly. No separate OCR is needed | On-device text recognition, or an OCR engine such as Tesseract, when privacy or cost demands it |

- **Names and voices live in settings, read from the environment**, never in code: `TRANSCRIPTION_MODEL`, `SPEECH_MODEL`, `SPEECH_VOICE`, `SPEECH_BASE_URL`.
- **Each provider sits behind a tiny interface** (`Transcriber`, `Speaker`) with a fake implementation for tests and for development without a key.
- **A retired model must fail loudly and clearly.** A 404 about an unknown model is *our* configuration problem, so it is reported to the developers and never blamed on the user’s file.
- **Watch the deprecation pages.** Put the shutdown dates of the models you use in your calendar and in your monitoring (Chapter 55).
- **Prefer a path that cannot be retired.** The phone’s own speech voice has no vendor to shut it down. We use it by default and offer the server voice as an upgrade.

## Images: Normalize Before You Send › The normalizer

`normalize_image` does eight things in a careful order. Read it as a checklist: refuse impossible sizes **before** decoding, decode with the memory-saving `draft` option for JPEG, keep one frame of an animation, bake the camera rotation into the pixels, drop all metadata by rebuilding the picture from raw pixels, resize, and encode to a byte budget.

**attachments/images.py**

```
def normalize_image(data: bytes, limits: MediaLimits | None = None) ->
    NormalizedImage:
    """Turn an untrusted picture into a small, clean, predictable one.

    - refuses pictures whose DECODED size would exhaust memory (a 30 KB file can
        claim 40000 x 40000 pixels)
    - applies the camera's rotation, then removes ALL metadata (GPS position,
        camera serial, timestamps)
    - keeps only the first frame of animations
    - resizes to what the model can actually use, which also caps the token cost
    - re-encodes: JPEG, or PNG when there is transparency
    """
    limits = limits or get_limits()
    try:
        # A decompression-bomb WARNING from Pillow becomes an error here, so it can
            never slip through.
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(data))
            original_width, original_height = img.size  # read from the header:
                nothing is decoded yet
            if original_width * original_height > limits.max_image_pixels:
                raise MediaRejected("image_too_many_pixels", "The picture has too
                    many pixels.")

            tier = limits.tier
            if img.format == "JPEG":
                # Let the decoder shrink the picture while it reads. Far less
                    memory for big photos.
                img.draft("RGB", (tier.max_edge * 2, tier.max_edge * 2))
            if getattr(img, "n_frames", 1) > 1:
                img.seek(0)
            img.load()
    except MediaRejected:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise MediaRejected("image_too_many_pixels", "The picture has too many
            pixels.") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise MediaRejected("unreadable_image", "The picture could not be read.")
            from None

    img = ImageOps.exif_transpose(img)  # bake the camera rotation into the pixels
    alpha = _has_alpha(img)
    img = img.convert("RGBA" if alpha else "RGB")

    target = resized_size(*img.size, tier=tier) if img.size[0] != 0 else img.size
    # `draft` may already have shrunk a JPEG below the original size; never scale
        UP.
    if img.size[0] * img.size[1] > target[0] * target[1] or max(img.size) >
        tier.max_edge:
        img = img.resize(target, Image.Resampling.LANCZOS)

    # A brand-new image object from raw pixels carries no metadata at all, whatever
        the source had.
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
```

**attachments/images.py (_encode)**

```
def _encode(img: Image.Image, alpha: bool, max_bytes: int) -> tuple[bytes, str]:
    """Encode, lowering JPEG quality and then the size until the result fits the
        byte budget."""
    for shrink in (1.0, 0.85, 0.7, 0.55):
        candidate = img if shrink == 1.0 else img.resize(
            (max(1, int(img.size[0] * shrink)), max(1, int(img.size[1] * shrink))),
                Image.Resampling.LANCZOS
        )
        qualities = (None,) if alpha else (85, 75, 65, 50)
        for quality in qualities:
            buffer = io.BytesIO()
            if alpha:
                candidate.save(buffer, format="PNG", optimize=True)
            else:
                candidate.save(buffer, format="JPEG", quality=quality,
                    optimize=True)
            if buffer.tell() <= max_bytes:
                return buffer.getvalue(), "image/png" if alpha else "image/jpeg"
    raise MediaRejected("image_too_complex", "The picture is too detailed to shrink
        to an acceptable size.")
```

> **Why rebuild the image from pixels?**
>
> How much metadata Pillow carries from a source picture into a saved one (camera data, colour profiles, text chunks) depends on the format and on the options you pass, and it is easy to get wrong. `Image.frombytes(mode, size, img.tobytes())` makes a brand-new image from raw pixels, so *nothing* from the source can survive, whatever the format. The cost is that colour profiles are dropped, so a wide-gamut photo can look a little duller if you display this copy. For a model that does not matter; if you show the copy to people, convert to sRGB first.

The tests are the proof. Here are three of the eleven: the bomb, the private metadata, and the rotation.

**attachments/test_images.py (excerpt)**

```
def test_a_decompression_bomb_is_refused_before_anything_is_decoded(self):
    data = png_claiming_size(40_000, 40_000)
    self.assertLess(len(data), 200)  # tiny file, 1.6 billion pixels claimed
    with self.assertRaises(MediaRejected) as ctx:
        normalize_image(data)
    self.assertEqual(ctx.exception.code, "image_too_many_pixels")

def test_gps_position_and_camera_data_are_removed(self):
    exif = Image.Exif()
    exif[0x010F] = "Acme Camera Co"  # make
    exif[0x0110] = "Model 9"
    exif[0x9003] = "2026:11:04 10:00:00"
    exif[0x8825] = {1: "N", 2: (6.0, 27.0, 0.0), 3: "E", 4: (3.0, 23.0, 0.0)}  #
        GPS IFD
    original = jpeg_bytes(exif=exif.tobytes())
    self.assertTrue(Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825),
        "test setup: GPS must be present")

    out = normalize_image(original)
    cleaned = Image.open(io.BytesIO(out.data))
    self.assertEqual(dict(cleaned.getexif()), {})
    self.assertNotIn(b"Acme", out.data)
    self.assertNotIn(b"Exif", out.data[:64])

def test_the_cameras_rotation_is_applied_to_the_pixels(self):
    exif = Image.Exif(); exif[0x0112] = 6  # "rotate 90 degrees clockwise to
        display"
    out = normalize_image(jpeg_bytes(size=(200, 100), exif=exif.tobytes()))
    self.assertEqual((out.width, out.height), (100, 200))
```

Note how the bomb test is built: a valid PNG header that **claims** 40,000 by 40,000 pixels, in less than 200 bytes. The file is tiny; the claim is the weapon. Refusing it requires only reading the header, which is why the size check comes before `load()`.


## Audio: Validating and Converting with ffmpeg

Phones record in one of several formats (AAC in an `.m4a` container on iOS and usually on Android, WebM in a browser), and speech models want something simpler. **ffmpeg** is the standard tool for converting between them, and **ffprobe**, which comes with it, reads a file’s duration and streams. Both are powerful and old, which makes them a risk if you feed them untrusted files carelessly. Five rules keep it safe.

1. **Pass arguments as a list.**  `subprocess.run(["ffmpeg", "-i", path, ...])` never goes through a shell, so a file name cannot inject a command.
2. **Allow only local files.**  `-protocol_whitelist file` stops a crafted playlist from making ffmpeg read other files or call a network address.
3. **Put a time limit on every call** (`timeout=`), and a limit on the output length (`-t`), because a file can lie about its duration.
4. **Take the first audio stream and nothing else.**  `-map 0:a:0 -vn -map_metadata -1` drops video and metadata, so an `.mp4` with a video track becomes plain sound.
5. **Install ffmpeg yourself and keep it updated.** It is a native program with a long history of security fixes. Add it to the backend image (Chapters 51 and 52) and rebuild regularly.
**attachments/audio.py**

```
_SAFE_INPUT = ["-protocol_whitelist", "file"]

@dataclass(frozen=True)
class AudioInfo:
    duration: float
    codec: str
    sample_rate: int
    channels: int
    has_video: bool

def _run(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Run a tool with a list of arguments (never a shell string) and a hard time
        limit."""
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout,
            check=False)
    except subprocess.TimeoutExpired:
        raise MediaRejected("audio_processing_timeout", "The audio took too long to
            process.") from None
    except FileNotFoundError as exc:  # our server is misconfigured, not the user's
        file
        raise RuntimeError(f"{args[0]} is not installed on this server") from exc

def probe_audio(path: str | Path, limits: MediaLimits | None = None, max_seconds:
    int | None = None,
                timeout: int = 20) -> AudioInfo:
    limits = limits or get_limits()
    max_seconds = max_seconds or limits.max_audio_seconds
    result = _run(
        ["ffprobe", "-v", "error", *_SAFE_INPUT, "-print_format", "json",
            "-show_format", "-show_streams", str(path)],
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
        raise MediaRejected("unreadable_audio", "The audio has no readable sound
            track.") from None
    if duration > max_seconds:
        raise MediaRejected("audio_too_long", f"The audio is longer than
            {max_seconds} seconds.")
    return AudioInfo(
        duration=duration,
        codec=str(audio.get("codec_name", "")),
        sample_rate=int(audio.get("sample_rate", 0) or 0),
        channels=int(audio.get("channels", 0) or 0),
        has_video=any(s.get("codec_type") == "video" for s in streams),
    )

def to_speech_wav(src: str | Path, dst: str | Path, max_seconds: int, timeout: int
    = 90) -> None:
    """Convert to what speech models like best: mono, 16 kHz, plain WAV. Also drops
        video and metadata,
    and never writes more than max_seconds, even if the file lied about its
        length."""
    result = _run(
        [
            "ffmpeg", "-nostdin", "-v", "error", *_SAFE_INPUT, "-i", str(src),
            "-map", "0:a:0", "-vn", "-map_metadata", "-1",
            "-ac", "1", "-ar", "16000", "-t", str(max_seconds),
            "-f", "wav", "-y", str(dst),
        ],
        timeout,
    )
    if result.returncode != 0 or not Path(dst).exists() or Path(dst).stat().st_size
        < 100:
        raise MediaRejected("unreadable_audio", "The audio could not be converted.")
```

We convert to mono, 16 kHz WAV because that is what most speech models expect internally: sending more is wasted bandwidth, and sending less loses accuracy. The tests use real ffmpeg to **create** their sample files (a sine tone in `.m4a`, `.mp3`, `.wav` and an `.mp4` with video) so they exercise the real tools instead of mocks.

**attachments/test_audio.py (excerpt)**

```
def test_a_video_file_is_noticed_and_only_its_sound_is_kept(self):
    mp4 = make_audio(self.dir / "clip.mp4", "-c:a", "aac", "-c:v", "mpeg4",
        "-shortest")
    self.assertTrue(probe_audio(mp4).has_video)
    out = self.dir / "out.wav"
    to_speech_wav(mp4, out, max_seconds=60)
    with wave.open(str(out)) as wav:  # a plain WAV file, so there is no video in it
        self.assertEqual((wav.getnchannels(), wav.getframerate()), (1, 16000))

def test_a_playlist_that_points_at_another_file_is_not_followed(self):
    secret = self.dir / "secret.txt"
    secret.write_text("top secret")
    playlist = self.dir / "list.m3u8"
    playlist.write_text(f"#EXTM3U\n#EXTINF:1,\n{secret}\n")
    with self.assertRaises(MediaRejected):
        probe_audio(playlist)

def test_conversion_never_writes_more_than_the_limit(self):
    src = make_audio(self.dir / "long.wav", seconds=5)
    out = self.dir / "short.wav"
    to_speech_wav(src, out, max_seconds=2)
    with wave.open(str(out)) as wav:
        self.assertLessEqual(wav.getnframes() / 16000, 2.05)
```


## The Attachment Pipeline: Models, Upload API and Celery › The worker

The task follows the rules of Chapter 15 and Chapter 25: **idempotent** (a finished attachment is left alone, and every step overwrites its own result), **one retry owner** (the provider SDK is told not to retry, Celery does), and **classified failures**. Only `ProviderUnavailable` is retried, with exponential backoff and jitter; everything permanent is written on the row.

**attachments/tasks.py (process)**

```
def process(attachment_id: int, transcriber: Transcriber | None = None) -> str:
    """Do the work. Safe to run twice: a finished attachment is left alone, and
        every step overwrites its own result.

    Raises ProviderUnavailable for failures that may pass (the Celery wrapper
        retries those).
    Everything permanent is recorded on the row and returns normally.
    """
    try:
        attachment = Attachment.objects.get(pk=attachment_id)
    except Attachment.DoesNotExist:
        return "missing"
    if attachment.status in FINISHED:
        return "already-finished"

    Attachment.objects.filter(pk=attachment.pk).update(status=Attachment.Status.PROC
        ESSING)
    limits = get_limits()
    try:
        data = attachment.original.read() if attachment.original else b""
        attachment.original.close()
        if attachment.kind == Attachment.Kind.IMAGE:
            _process_image(attachment, data)
        elif attachment.kind == Attachment.Kind.DOCUMENT:
            _process_pdf(attachment, data)
        else:
            _process_audio(attachment, data, transcriber or get_transcriber(),
                limits.max_audio_seconds)
    except MediaRejected as exc:
        _finish(attachment, Attachment.Status.REJECTED, exc.code)
        return "rejected"
    except ProviderUnavailable:
        raise  # not finished: the wrapper retries, and `FINISHED` stays false in
            the meantime
    except ProviderConfigError:
        logger.error("speech provider misconfigured", extra={"attachment":
            attachment.pk})
        _finish(attachment, Attachment.Status.FAILED, "provider_config")
        return "failed"
    except Exception:
        # A bug of ours. Log the type and the id: never the content, which is the
            user's private data.
        logger.exception("attachment processing crashed", extra={"attachment":
            attachment.pk})
        _finish(attachment, Attachment.Status.FAILED, "internal_error")
        return "failed"

    # Privacy by default: once the cleaned copy (or the transcript) exists, the raw
        original, with its
    # metadata, is deleted. A PDF is the exception because the model reads that
        very file.
    if attachment.kind != Attachment.Kind.DOCUMENT and attachment.original:
        attachment.original.delete(save=False)
        attachment.original = None
    attachment.status, attachment.error_code = Attachment.Status.READY, ""
    attachment.save()
    return "ready"
```

**attachments/tasks.py (the Celery wrapper)**

```
@shared_task(bind=True, max_retries=4, acks_late=True)
def process_attachment(self, attachment_id: int):
    try:
        return process(attachment_id)
    except ProviderUnavailable as exc:
        if self.request.retries >= self.max_retries:
            Attachment.objects.filter(pk=attachment_id).update(status=Attachment.Sta
                tus.FAILED, error_code="provider_unavailable")
            return "failed"
        # exponential backoff with jitter, as in Chapter 25: 5 s, 10 s, 20 s, 40 s,
            each randomised
        from random import random
        raise self.retry(exc=exc, countdown=(5 * 2 ** self.request.retries) * (0.5
            + random() / 2))
```

> **Privacy by default: delete what you no longer need**
>
> Look at the lines that run after processing: once the cleaned picture or the transcript exists, **the original is deleted**. A raw photo with its metadata, or a voice recording, is more sensitive than anything derived from it, and keeping it “just in case” is a liability you pay for in storage, in breach risk and in trust. A PDF is the exception because the model reads that very file. And when processing fails, nothing private is left behind either.


## Speech-to-Text: Dictation and Transcription › The provider adapter

The adapter is deliberately small. It sends the WAV file and the configured model name, and it sorts every possible failure into one of three kinds so the rest of the code never needs to know a vendor’s exception types.

| **The provider says** | **We treat it as** | **What happens** |
|---|---|---|
| Timeout, dropped connection, 429, 5xx | `ProviderUnavailable` | Dictation: a clear 503 the app can retry. Pipeline: Celery retries with backoff |
| 401, 403 or **404** (a wrong key, or a model name that was retired) | `ProviderConfigError` | Logged for the developers. The user sees a calm “not available”. The file is **not** blamed |
| 400 (the audio was refused) | `MediaRejected` | The user is told that this recording could not be used |

**attachments/providers.py (transcriber)**

```
def _translate(exc: Exception):
    """Sort a provider failure into the three kinds our code knows how to handle."""
    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError,
        openai.RateLimitError)):
        return ProviderUnavailable(type(exc).__name__)
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code >= 500 or exc.status_code in (408, 409, 429):
            return ProviderUnavailable(f"status {exc.status_code}")
        if exc.status_code in (401, 403, 404):  # wrong key, no access, or a model
            name that no longer exists
            return ProviderConfigError(f"provider answered {exc.status_code}: check
                the key and the model name")
        return MediaRejected("provider_rejected", "The speech service could not use
            this audio.")
    return exc

def make_client(*, api_key: str, base_url: str | None = None, timeout: float =
    30.0) -> OpenAI:
    """max_retries=0 on purpose: Celery (or the caller) retries. Retry in exactly
        one place."""
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout,
        max_retries=0)

class OpenAICompatibleTranscriber:
    """Works with any server that speaks the same /audio/transcriptions protocol,
        hosted or self-hosted."""

    def __init__(self, client: OpenAI, model: str):
        self.client, self.model = client, model

    def transcribe(self, wav: bytes, *, language: str | None = None) -> Transcript:
        params = {"model": self.model, "file": ("audio.wav", io.BytesIO(wav),
            "audio/wav")}
        if language:
            params["language"] = language  # a known language improves accuracy and
                speed
        try:
            result = self.client.audio.transcriptions.create(**params)
        except Exception as exc:
            raise _translate(exc) from exc
        return Transcript(text=(result.text or "").strip(), language=language)
```

> **Hosted or self-hosted: the same adapter**
>
> The adapter speaks the common `/audio/transcriptions` protocol through the OpenAI SDK with a configurable `base_url`. Several vendors and self-hosted servers implement that same protocol, so moving from a hosted service to an open-weight model such as Whisper that you run yourself can be a settings change, if the server you choose speaks it. Check the compatibility of the specific server; do not assume it. `max_retries=0` on the client is deliberate: retrying belongs to Celery, in one place (Chapter 25).

**attachments/test_providers.py (excerpt)**

```
def test_request_has_the_model_the_file_and_the_language(self):
    seen = {}

    def handler(request: httpx.Request):
        seen["path"], seen["body"] = request.url.path, request.read()
        return httpx.Response(200, json={"text": "  hello world  "})

    result = OpenAICompatibleTranscriber(client_with(handler),
        model="my-model").transcribe(b"RIFFwavbytes", language="en")
    self.assertEqual(seen["path"], "/v1/audio/transcriptions")
    for needle in (b'name="model"', b"my-model", b'filename="audio.wav"',
        b'name="language"', b"RIFFwavbytes"):
        self.assertIn(needle, seen["body"])
    self.assertEqual(result.text, "hello world")

def test_failures_are_sorted_into_retry_fix_or_reject(self):
    def failing(status):
        return lambda request: httpx.Response(status, json={"error": {"message":
            "nope"}})

    transcribe = lambda handler: OpenAICompatibleTranscriber(client_with(handler),
        model="m").transcribe(b"abc")  # noqa: E731
    for status in (429, 500, 502, 503):
        with self.assertRaises(ProviderUnavailable, msg=str(status)):
            transcribe(failing(status))
    for status in (401, 403, 404):  # wrong key or a model name that has been
        retired
        with self.assertRaises(ProviderConfigError, msg=str(status)):
            transcribe(failing(status))
    with self.assertRaises(MediaRejected):
        transcribe(failing(400))
```


## Text-to-Speech: Speaking the Reply

Reading answers aloud helps people who are driving, cooking or have low vision, and it is also where the cost can surprise you: you pay per character, and an assistant’s answers are long. Three design choices keep it cheap and pleasant.

1. **Clean the text first.** A voice reading “asterisk asterisk bold asterisk asterisk” or a web address letter by letter is unbearable. Markdown marks vanish, links keep their label, bare addresses become “a link”, and code blocks become “code omitted”.
2. **Cut at sentence ends.** Providers limit the input length (the OpenAI speech endpoint accepts about 4,000 characters), and a cut in the middle of a sentence sounds broken.
3. **Cache by content.** The same text with the same voice sounds the same, so we synthesise it once. Hashing the model, voice, format and text gives a key; a second request, from this or any other user, is a file read.
**attachments/speech_text.py**

```
MAX_SPEECH_CHARS = 4000  # stay under typical provider input limits (OpenAI's
    speech endpoint allows 4096)

def to_speakable(markdown: str) -> str:
    """Text a voice can read. A synthesiser reading "asterisk asterisk" or a URL
        letter by letter is awful."""
    text = markdown
    text = re.sub(r"```.*?```", " (code omitted) ", text, flags=re.S)          #
        fenced code blocks
    text = re.sub(r"`([^`]*)`", r"\1", text)                                   #
        inline code: keep the words
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)                      #
        images: keep the alt text
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)                       #
        links: keep the label, drop the URL
    text = re.sub(r"https?://\S+", "a link", text)                             #
        bare URLs
    text = re.sub(r"^[ \t]{0,3}#{1,6}[ \t]*", "", text, flags=re.M)
        # heading marks
    text = re.sub(r"^[ \t]*[-*+][ \t]+", "", text, flags=re.M)
        # bullets
    text = re.sub(r"^[ \t]*\d+[.)][ \t]+", "", text, flags=re.M)
        # numbered lists
    text = re.sub(r"(\*\*|__|\*|_)(.+?)\1", r"\2", text)                       #
        bold and italics
    text = re.sub(r"^[ \t]*>[ \t]?", "", text, flags=re.M)
        # quotes
    text = re.sub(r"\|", " ", text)                                            #
        table bars
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()

def split_for_speech(text: str, max_chars: int = MAX_SPEECH_CHARS) -> list[str]:
    """Cut at paragraph and sentence ends so every piece sounds natural and fits
        the provider's limit."""
    if len(text) <= max_chars:
        return [text] if text else []
    sentences = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    parts, current = [], ""
    for sentence in sentences:
        while len(sentence) > max_chars:  # one enormous "sentence": cut at a space
            cut = sentence.rfind(" ", 0, max_chars) or max_chars
            cut = cut if cut > 0 else max_chars
            if current:
                parts.append(current); current = ""
            parts.append(sentence[:cut].strip()); sentence = sentence[cut:].strip()
        if len(current) + len(sentence) + 1 > max_chars and current:
            parts.append(current); current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts
```

The bug in the first version of `to_speakable` is a good lesson. The list-marker pattern used `\s*` (“any whitespace”), which also matches **newlines**, so it swallowed the blank lines before each bullet and the paragraphs ran together. The test with a heading, bullets and a numbered list caught it. Inside a line, write `[ \t]*`, not `\s*`.

**attachments/speech_service.py (speak_message)**

```
def speech_parts(message: Message) -> list[str]:
    return split_for_speech(to_speakable(message.content))

def speak_message(*, user, message_id, part: int, speaker: Speaker, model: str,
    voice: str, audio_format: str = "mp3"):
    """Audio for one part of an assistant message. Identical text is only ever
        synthesised once: the second
    request, from this or any other user, is a file read. Returns (audio_bytes,
        number_of_parts)."""
    message = Message.objects.select_related("conversation").get(
        public_id=message_id, conversation__user=user, role="assistant"  #
            owner-scoped, like everything else
    )
    parts = speech_parts(message)
    if not parts:
        raise MediaRejected("nothing_to_say", "There is no text to read.")
    if not 0 <= part < len(parts):
        raise MediaRejected("bad_part", "That part does not exist.")

    text = parts[part]
    key = hashlib.sha256(f"{model}|{voice}|{audio_format}|{text}".encode()).hexdiges
        t()
    path = f"speech-cache/{key}.{audio_format}"
    if default_storage.exists(path):
        with default_storage.open(path) as cached:
            return cached.read(), len(parts)

    audio = speaker.synthesize(text, voice=voice, audio_format=audio_format)
    default_storage.save(path, ContentFile(audio))
    return audio, len(parts)
```

The endpoint is owner-scoped and only reads aloud **assistant** messages that belong to the caller. The phone first asks `?info=1`, which returns the number of parts and costs nothing, then plays part 0, 1, 2 in turn.

**attachments/test_speech_api.py (excerpt)**

```
def test_the_same_text_is_synthesised_only_once(self):
    speaker = FakeSpeaker()
    with self.patched(speaker):
        self.client.get(self.url())
        second = self.client.get(self.url())
    self.assertEqual(second.status_code, 200)
    self.assertEqual(len(speaker.calls), 1)

def test_other_peoples_messages_and_your_own_prompts_cannot_be_read_aloud(self):
    mine = make_message(self.user, "user", "my own question")
    with self.patched(FakeSpeaker()):
        self.assertEqual(self.client.get(self.url(mine)).status_code, 404)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url()).status_code, 404)
```

> **Say when a voice is synthetic, and cap what it can cost**
>
> Do not present a synthetic voice as a human. A short label such as “Read by the assistant’s voice” is honest and costs nothing; Chapter 34 covers disclosure and consent properly. Also give the feature a budget: a per-user daily limit on characters spoken, enforced the same way as the upload limits, and an alert on spend (Chapter 33).


## Capturing Media on the Phone › Prepare before you upload

A 12-megapixel photo is several megabytes; at the size the model can use it is a few hundred kilobytes. Shrinking on the phone saves the user’s data and time, and makes the upload far less likely to fail on a weak connection (Chapter 25). The server cleans and checks the picture again anyway, so this step is a courtesy, not a defence: never skip the server checks because the phone “already” did it.

**mobile/lib/media/limits.ts**

```
export const MEDIA_LIMITS = {
  /** Longest side of a picture we upload. Matches what the model can use, so more
      pixels are wasted data. */
  maxImageEdge: 1568,
  jpegQuality: 0.8,
  maxImageBytes: 10 * 1024 * 1024,
  maxPdfBytes: 20 * 1024 * 1024,
  maxDictationSeconds: 60,
  maxAttachmentsPerMessage: 5,
} as const;
```

**mobile/lib/media/fit.ts**

```
export interface Size {
  width: number;
  height: number;
}

/** The size that fits inside `maxEdge` on the long side, same shape, never larger
    than the original. */
export function fitWithin(width: number, height: number, maxEdge: number): Size {
  if (width <= 0 || height <= 0) throw new Error('an image needs a positive size');
  const longest = Math.max(width, height);
  if (longest <= maxEdge) return { width, height };
  const scale = maxEdge / longest;
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1,
      Math.round(height * scale)) };
}
```

**mobile/lib/media/prepareImage.ts**

```
export interface PickedImage {
  uri: string;
  width: number;
  height: number;
}

/**
 * Shrink a photo on the phone before it is uploaded. A 12-megapixel camera photo
     is about 4 MB; at the size
 * the model can use it is a few hundred KB, which matters a great deal on a slow
     or paid connection.
 * The server cleans and checks the picture again: this step only saves time and
     data.
 */
export async function prepareImage(asset: PickedImage): Promise<LocalFile & {
    width: number; height: number }> {
  const target = fitWithin(asset.width, asset.height, MEDIA_LIMITS.maxImageEdge);
  const context = ImageManipulator.manipulate(asset.uri);
  if (target.width !== asset.width) context.resize({ width: target.width }); //
      height follows: the shape is kept
  const image = await context.renderAsync();
  const saved = await image.saveAsync({ format: SaveFormat.JPEG, compress:
      MEDIA_LIMITS.jpegQuality });
  return { uri: saved.uri, name: 'photo.jpg', mimeType: 'image/jpeg', width:
      saved.width, height: saved.height };
}
```

The phone shrinks to 1568 pixels on the long side, which is cheap and always safe. The server then finishes with the exact fit for the token budget, so the two steps do not need to agree to the pixel.


## Capturing Media on the Phone › Upload with a deadline and honest errors

The upload helper reuses the networking from Chapter 25 (`requestJson`, deadlines, `ApiError`) and adds three rules specific to files. It never sets `Content-Type` by hand, because a multipart body needs a boundary that is added automatically, and writing the header yourself removes it. It is **not** retried automatically, because a repeated upload is a second attachment; the user taps “Try again”. And it turns the server’s reason codes into plain sentences. The one change needed in the Chapter 25 client is a three-line export so uploads can read the base URL and the token.

**mobile/lib/api/client.ts (added in Chapter 32)**

```
/** NEW in Chapter 32: uploads need the base URL and the token, but not JSON
    encoding. */
export function getApiConfig(): ApiConfig {
  if (!config) throw new Error('Call configureApi() before the first request.');
  return config;
}
```

**mobile/lib/media/upload.ts**

```
export interface LocalFile {
  uri: string;
  name: string;
  mimeType: string;
}

/** A refusal from the server, with the words to show. `code` is the server's
    reason. */
export class UploadError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly canTryAgain: boolean,
  ) {
    super(message);
    this.name = 'UploadError';
  }
}

interface FormLike {
  append(name: string, value: unknown): void;
}

/**
 * React Native's FormData accepts { uri, name, type } for a file on the phone and
     hands the file to the
 * native networking layer, instead of reading it into JavaScript memory. (Browsers
     want a Blob instead; that is why
 * the constructor is injectable: the tests pass a fake.)
 */
export function createForm(
  file: LocalFile,
  fields: Record<string, string> = {},
  FormDataImpl: new () => FormLike = FormData as unknown as new () => FormLike,
): FormLike {
  const form = new FormDataImpl();
  form.append('file', { uri: file.uri, name: file.name, type: file.mimeType });
  for (const [name, value] of Object.entries(fields)) form.append(name, value);
  return form;
}

export interface UploadOptions<T> {
  fields?: Record<string, string>;
  /** Default 60 s: uploads are slower than ordinary calls. */
  timeoutMs?: number;
  signal?: AbortSignal | null;
  parse?: (data: unknown) => T;
  FormDataImpl?: new () => FormLike;
}

/**
 * POST a file as multipart/form-data.
 * - never sets Content-Type by hand: the multipart boundary is added
     automatically, and setting it breaks the upload
 * - is NOT retried automatically: a repeated upload is a second attachment. The
     user taps "Try again".
 * - turns the server's refusal codes into a plain sentence
 */
export async function uploadFile<T = unknown>(path: string, file: LocalFile,
    options: UploadOptions<T> = {}): Promise<T> {
  const { baseUrl, getToken, onUnauthorized, fetchImpl } = getApiConfig();
  const token = await getToken();
  try {
    return await requestJson<T>(`${baseUrl}${path}`, {
      method: 'POST',
      body: createForm(file, options.fields, options.FormDataImpl) as unknown as
          FormData,
      headers: { Accept: 'application/json', ...(token ? { Authorization: `Bearer
          ${token}` } : {}) },
      timeoutMs: options.timeoutMs ?? 60_000,
      signal: options.signal,
      parse: options.parse,
      fetchImpl,
    });
  } catch (error) {
    if (isUnauthorized(error)) onUnauthorized?.();
    const code = error instanceof ApiError && error.kind === 'http' ? (error.body
        as { code?: unknown } | undefined)?.code : undefined;
    if (typeof code === 'string') throw new UploadError(code, messageForCode(code),
        canTryAgain(code));
    throw error; // network, timeout and the rest: the screen shows
        userMessage(error)
  }
}
```

**mobile/lib/media/uploadMessages.ts (excerpt)**

```
const MESSAGES: Record<string, string> = {
  no_file: 'Nothing was attached. Please try again.',
  file_too_large: 'That file is too large. Try a smaller one.',
  unsupported_type: 'That type of file is not supported. You can share pictures,
      PDFs and voice recordings.',
  heic_not_supported: 'That photo is in a format we cannot read yet. Please share
      it as a JPEG.',
  // ... one plain sentence for every code the server can send ...
};

export const KNOWN_CODES = Object.keys(MESSAGES);

const GENERIC = 'That did not work. Please try again.';

export function messageForCode(code: unknown): string {
  return typeof code === 'string' && code in MESSAGES ? MESSAGES[code] : GENERIC;
}

/** Codes where trying the same thing again a little later can succeed. */
const RETRY_LATER = new Set(['speech_unavailable', 'provider_unavailable',
    'audio_processing_timeout', 'internal_error']);

export const canTryAgain = (code: unknown): boolean => typeof code === 'string' &&
    RETRY_LATER.has(code);
```

A test keeps the two sides honest: it lists every code the Django code can send and fails if one has no wording, and it checks that no sentence contains a raw code or a status number.

**mobile/__tests__/upload.test.ts (excerpt)**

```
it('posts the form with the token, and does NOT set a content type (the boundary is
    added for us)', async () => {
  const result = await uploadFile<{ text: string }>('/dictation/', file, {
      FormDataImpl: FakeForm });
  assert.deepEqual(result, { text: 'hello' });
  const { url, init } = calls[0];
  assert.equal(url, 'https://api.test/api/v1/dictation/');
  assert.equal(init.method, 'POST');
  const headers = init.headers as Record<string, string>;
  assert.equal(headers.Authorization, 'Bearer tok');
  assert.equal(Object.keys(headers).some((h) => h.toLowerCase() ===
      'content-type'), false);
  assert.ok(init.body instanceof FakeForm);
});

it('turns a refusal code from the server into a plain sentence', async () => {
  answer = () => json({ code: 'heic_not_supported', detail: 'x' }, { status: 415 });
  await assert.rejects(uploadFile('/attachments/', file, { FormDataImpl: FakeForm
      }), (e: UploadError) => {
    return e instanceof UploadError && e.code === 'heic_not_supported' &&
        /JPEG/.test(e.message) && e.canTryAgain === false;
  });
});
```


## Capturing Media on the Phone › Picking files, and watching the status

`AttachmentPicker` offers three ways to add a file (photo library, camera, PDF). `useAttachments` uploads the file, then asks the status endpoint with growing pauses (1 s, 1.5 s, 2 s, up to 5 s) until the attachment is ready or refused, and gives up after about two minutes. The screen only enables Send when nothing is still busy, and it sends the ids of the **ready** attachments.

**mobile/hooks/useAttachments.ts**

```
export type AttachmentStage = 'uploading' | 'processing' | 'ready' | 'error';

export interface PendingAttachment {
  localId: string;
  name: string;
  stage: AttachmentStage;
  /** The server's id, once the upload has been accepted. This is what the message
      refers to. */
  id?: string;
  error?: string;
}

interface ServerAttachment {
  id: string;
  status: 'uploaded' | 'processing' | 'ready' | 'rejected' | 'failed';
  error_code: string;
}

const MAX_POLLS = 40; // a bit over two minutes; then we stop asking and say so

export function useAttachments() {
  const [items, setItems] = useState<PendingAttachment[]>([]);
  const counter = useRef(0);

  const patch = useCallback((localId: string, change: Partial<PendingAttachment>)
      => {
    setItems((current) => current.map((i) => (i.localId === localId ? { ...i,
        ...change } : i)));
  }, []);

  const add = useCallback(
    async (file: LocalFile) => {
      if (items.length >= MEDIA_LIMITS.maxAttachmentsPerMessage) return;
      const localId = `local-${++counter.current}`;
      setItems((current) => [...current, { localId, name: file.name, stage:
          'uploading' }]);
      try {
        const accepted = await uploadFile<ServerAttachment>('/attachments/', file);
        patch(localId, { id: accepted.id, stage: 'processing' });
        for (let attempt = 0; attempt < MAX_POLLS; attempt++) {
          await new Promise((resolve) => setTimeout(resolve,
              nextPollDelay(attempt)));
          const current = await
              apiRequest<ServerAttachment>(`/attachments/${accepted.id}/`);
          if (current.status === 'ready') return patch(localId, { stage: 'ready' });
          if (current.status === 'rejected' || current.status === 'failed') {
            return patch(localId, { stage: 'error', error: new
                UploadError(current.error_code, '', false).code });
          }
        }
        patch(localId, { stage: 'error', error: 'timeout' });
      } catch (error) {
        patch(localId, { stage: 'error', error: error instanceof UploadError ?
            error.code : userMessage(error) });
      }
    },
    [items.length, patch],
  );

  const remove = useCallback((localId: string) => setItems((current) =>
      current.filter((i) => i.localId !== localId)), []);
  const readyIds = items.filter((i) => i.stage === 'ready' && i.id).map((i) => i.id
      as string);
  const busy = items.some((i) => i.stage === 'uploading' || i.stage ===
      'processing');

  return { items, add, remove, readyIds, busy };
}
```

**mobile/components/AttachmentPicker.tsx (excerpt)**

```
  const fromLibrary = async () => {
    // On current versions of both systems the system photo picker usually needs no
        permission prompt.
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes:
        ['images'], quality: 1, exif: false });
    if (result.canceled || !result.assets[0]) return;
    onFile(await prepareImage(result.assets[0]));
  };

  const fromCamera = async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) return Alert.alert('Camera access is off', 'You can
        allow it in Settings.');
    const result = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'],
        quality: 1, exif: false });
    if (result.canceled || !result.assets[0]) return;
    onFile(await prepareImage(result.assets[0]));
  };

  // ... fromFiles picks a PDF and checks its size the same way ...
```

> **What about offline?**
>
> Chapter 25’s outbox keeps **messages** safe while offline. Files are different: they are large, they need the user’s attention to confirm, and a queue of forgotten 8 MB uploads on a mobile connection is a nasty surprise. The simple and honest design is to disable the attach buttons offline with a short reason (“Attachments need a connection”) and to keep the text message flow as it is. If you want to queue small files, store the prepared JPEG in the app’s cache folder, put the *path* in the outbox and upload when the network returns (exercise 6).


## Voice on the Phone: Dictation and Reading Aloud › The hook

The hook is three small effects driven by the phase: one asks for the permission and starts the recorder, one counts seconds, and one stops, uploads and reports. Every effect cleans up after itself, and the upload effect aborts when the phase changes, so a late answer after Cancel is ignored in the UI as well as in the reducer. The recognised text goes **into the text box**, never straight to the assistant.

**mobile/hooks/useDictation.ts**

```
import { requestRecordingPermissionsAsync, setAudioModeAsync, useAudioRecorder }
    from 'expo-audio';
import { useCallback, useEffect, useReducer } from 'react';
import { userMessage } from '../lib/net/errors';
import { dictationReducer, initialDictation, type DictationEvent, type
    DictationState } from '../lib/media/dictationState';
import { SPEECH_RECORDING } from '../lib/media/recording';
import { UploadError, uploadFile } from '../lib/media/upload';

// useReducer wants a reducer of exactly (state, event); our function also takes an
    optional limit, so wrap it.
const reducer = (state: DictationState, event: DictationEvent) =>
    dictationReducer(state, event);

const parseText = (data: unknown): { text: string } => {
  const text = (data as { text?: unknown })?.text;
  if (typeof text !== 'string') throw new Error('unexpected answer');
  return { text };
};

/**
 * Press once to start, press again to stop; the words appear in the text box for
     the user to check and send.
 * We never send a transcript on the user's behalf: speech recognition makes
     mistakes, and a human must see them.
 */
export function useDictation(onText: (text: string) => void) {
  const recorder = useAudioRecorder(SPEECH_RECORDING);
  const [state, dispatch] = useReducer(reducer, initialDictation);

  // asking -> ask the system for the microphone, then start recording
  useEffect(() => {
    if (state.phase !== 'asking') return;
    let alive = true;
    void (async () => {
      const permission = await requestRecordingPermissionsAsync();
      if (!alive) return;
      if (permission.granted) {
        await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
        await recorder.prepareToRecordAsync();
        recorder.record();
      }
      dispatch({ type: 'permission', granted: permission.granted });
    })();
    return () => {
      alive = false;
    };
  }, [state.phase, recorder]);

  // recording -> one tick a second; the reducer stops by itself at the limit
  useEffect(() => {
    if (state.phase !== 'recording') return;
    const timer = setInterval(() => dispatch({ type: 'tick' }), 1000);
    return () => clearInterval(timer);
  }, [state.phase]);

  // uploading -> stop the recorder, send the file, report the result
  useEffect(() => {
    if (state.phase !== 'uploading') return;
    const controller = new AbortController();
    void (async () => {
      try {
        await recorder.stop();
        await setAudioModeAsync({ allowsRecording: false });
        const uri = recorder.uri;
        if (!uri) throw new Error('no recording');
        const { text } = await uploadFile('/dictation/', { uri, name:
            'dictation.m4a', mimeType: 'audio/mp4' }, { signal: controller.signal,
            timeoutMs: 45_000, parse: parseText });
        dispatch({ type: 'uploaded', text });
        onText(text);
      } catch (error) {
        if (controller.signal.aborted) return;
        const known = error instanceof UploadError;
        dispatch({ type: 'failed', message: known ? error.message :
            userMessage(error), canTryAgain: known ? error.canTryAgain : true });
      }
    })();
    return () => controller.abort(); // cancelled or unmounted: the answer is no
        longer wanted
  }, [state.phase, recorder, onText]);

  const press = useCallback(() => dispatch({ type: 'press' }), []);
  const cancel = useCallback(() => {
    void recorder.stop().catch(() => undefined); // throw the recording away
    dispatch({ type: 'cancel' });
  }, [recorder]);

  return { state, press, cancel };
}
```

**mobile/components/DictationButton.tsx (excerpt)**

```
export function DictationButton({ onText }: { onText: (text: string) => void }) {
  const { state, press, cancel } = useDictation(onText);
  const busy = state.phase === 'asking' || state.phase === 'uploading';
  const label = state.phase === 'recording' ? `Stop recording, ${state.seconds}
      seconds` : 'Dictate a message';

  return (
    <View>
      <View style={styles.row}>
        <Pressable accessibilityRole="button" accessibilityLabel={label}
            disabled={busy} onPress={press} style={[styles.button, state.phase ===
            'recording' && styles.recording]}>
          {busy ? <ActivityIndicator color="#FFFFFF" /> : <Text
              style={styles.icon}>{state.phase === 'recording' ? '■' : '🎤'}</Text>}
        </Pressable>
        {state.phase === 'recording' ? (
          <>
            <Text accessibilityLiveRegion="polite"
                style={styles.timer}>{`0:${String(state.seconds).padStart(2,
                '0')}`}</Text>
            <Pressable accessibilityRole="button" onPress={cancel} hitSlop={8}>
              <Text style={styles.cancel}>Cancel</Text>
            </Pressable>
          </>
        ) : null}
      </View>
      {state.phase === 'error' && state.error ? (
        <View accessibilityRole="alert">
          <Text style={styles.error}>{state.error.message}</Text>
          {state.error.needsSettings ? (
            <Pressable accessibilityRole="button" onPress={() => void
                Linking.openSettings()}>
              <Text style={styles.cancel}>Open Settings</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}
```

- **Not only hold-to-talk.** Holding a button is hard for people with motor impairments; tap to start and tap to stop works for everyone.
- **Show that it is listening.** A timer and a changed button; announce the state to screen readers (`accessibilityLiveRegion`).
- **Switch the audio mode back.** After recording, `allowsRecording: false`, so other sound on the phone returns to normal.
- **Expect interruptions.** A phone call stops the recorder; treat an empty or missing file as a failed recording, not a crash.
- **Never send automatically.** The user reads the words first.

## Voice on the Phone: Dictation and Reading Aloud › Reading replies aloud

The default is the **phone’s own voice**: free, private, works offline and cannot be retired by a vendor. The hook cleans the text, cuts it below the engine’s maximum input length and speaks the pieces one after another. Each reading has a generation number, so tapping Stop (or leaving the screen) makes callbacks from the old reading harmless.

**mobile/hooks/useReadAloud.ts (device voice)**

```
export function useDeviceSpeech() {
  const [speaking, setSpeaking] = useState(false);
  const queue = useRef<string[]>([]);
  const generation = useRef(0); // stop() bumps it, so callbacks from the old
      reading are ignored

  const next = useCallback((id: number, language?: string) => {
    if (id !== generation.current) return;
    const text = queue.current.shift();
    if (text === undefined) return setSpeaking(false);
    Speech.speak(text, {
      language,
      onDone: () => next(id, language),
      onStopped: () => {
        if (id === generation.current) setSpeaking(false);
      },
      onError: () => {
        if (id === generation.current) setSpeaking(false);
      },
    });
  }, []);

  const stop = useCallback(() => {
    generation.current++;
    queue.current = [];
    Speech.stop();
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    (markdown: string, language?: string) => {
      stop();
      queue.current = splitForSpeech(toSpeakable(markdown),
          Math.min(Speech.maxSpeechInputLength, 3000));
      if (queue.current.length === 0) return;
      setSpeaking(true);
      next(generation.current, language);
    },
    [next, stop],
  );

  useEffect(() => stop, [stop]); // leaving the screen silences the voice
  return { speak, stop, speaking };
}
```

For a better voice, the same file has `useServerSpeech`: it asks `?info=1` for the number of parts (free), then plays each part from the protected endpoint. `expo-audio` can send headers with a remote source, so the token travels in an `Authorization` header and nothing is written to disk. Offer it as an option, because each *new* message costs money; the cache means the second listener to the same reply costs nothing.

**mobile/hooks/useReadAloud.ts (server voice, excerpt)**

```
  const playPart = useCallback(
    (index: number) => {
      const { baseUrl, getToken } = getApiConfig();
      void getToken().then((token) => {
        part.current = index;
        // expo-audio can send headers with a remote source, so the protected
            endpoint is streamed directly
        player.replace({ uri:
            `${baseUrl}/messages/${messageId}/speech/?part=${index}`, headers:
            token ? { Authorization: `Bearer ${token}` } : {} });
        player.play();
      });
    },
    [messageId, player],
  );
```

The text cleaning exists in two places, Python on the server and TypeScript on the phone, because each side must clean the text it speaks. To keep them in step, **the same test cases run on both**: compare `test_speech_text.py` with `speakable.test.ts`. When you change a rule, change both tests first.


## Computer Vision Basics for Camera and Sensor Apps › The budget: time, battery and heat

| **Constraint** | **Number to keep in mind** | **What to do** |
|---|---|---|
| **Frame time** | At 30 frames per second you have about 33 ms per frame for everything | Do not process every frame: 5 to 10 a second is enough for most features |
| **Battery and heat** | The camera plus a model is one of the most power-hungry things a phone does | Run only while the screen needs it; stop when the user leaves; lower the rate when the phone is warm |
| **Memory** | Frames are large | Reuse buffers; never keep frames in React state |
| **Upload cost** | A full-size frame is megabytes | Send a cropped, shrunk still, not a video stream |

*(figure: see the printed book)*

> **On-device models usually need a development build**
>
> Expo Go contains a fixed set of native modules. Camera scanning of barcodes and QR codes works through `expo-camera`, but running your own neural network on camera frames needs native code (a frame-processor library or an on-device inference runtime) and therefore a development build (Chapter 26). Decide early, because it changes your workflow. The rest of this chapter’s CV code, the clean-up and the geometry, is plain TypeScript and works with any detector you choose.

A last point on privacy: a model running on the phone means the picture never leaves it. For faces, documents and anything inside a home, that is often the strongest privacy feature you can offer. Say so in the interface when it is true. In Chapter 58 (the farm and IoT project) the same ideas apply to field cameras and sensors that may have no connection at all.


## Detection Post-Processing You Can Test

Whatever detector you use, the same four problems appear. Each has a small, exact solution.


### Problem 1: the same object reported many times

Detectors propose many overlapping boxes. To decide whether two boxes are the same object, measure how much they overlap relative to their combined area: **intersection over union**, IoU. It is 0 for boxes that do not touch and 1 for identical boxes. **Non-maximum suppression** (NMS) then keeps the box with the best score, drops its near-duplicates, and repeats. Only boxes with the **same label** compete: a cup box on top of a table box is not a duplicate.

**mobile/lib/cv/geometry.ts (IoU and NMS)**

```
export interface Box {
  /** Top-left corner, in pixels. */
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Detection {
  box: Box;
  /** 0 to 1: how sure the model is. It is NOT a probability you can trust blindly
      (see section 32.13). */
  score: number;
  label: string;
}

export interface Size {
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

/** Intersection over union: 0 = the boxes do not touch, 1 = identical. The
    standard way to ask "same object?". */
export function iou(a: Box, b: Box): number {
  const overlapWidth = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const overlapHeight = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y,
      b.y);
  if (overlapWidth <= 0 || overlapHeight <= 0) return 0;
  const intersection = overlapWidth * overlapHeight;
  const union = a.width * a.height + b.width * b.height - intersection;
  return union > 0 ? intersection / union : 0;
}

export interface NmsOptions {
  /** Drop detections below this score first. */
  scoreThreshold?: number;
  /** Two boxes of the same label overlapping more than this are the same object:
      keep the better one. */
  iouThreshold?: number;
  maxDetections?: number;
}

/**
 * Non-maximum suppression. A detector usually reports the same object several
     times with slightly different
 * boxes. Keep the highest score, drop its near-duplicates, repeat. Only boxes with
     the SAME label compete:
 * a "cup" box overlapping a "table" box is not a duplicate.
 */
export function nms(detections: Detection[], { scoreThreshold = 0.3, iouThreshold =
    0.5, maxDetections = 20 }: NmsOptions = {}): Detection[] {
  const candidates = detections.filter((d) => d.score >= scoreThreshold).sort((a,
      b) => b.score - a.score);
  const kept: Detection[] = [];
  for (const candidate of candidates) {
    if (kept.length >= maxDetections) break;
    const duplicate = kept.some((k) => k.label === candidate.label && iou(k.box,
        candidate.box) > iouThreshold);
    if (!duplicate) kept.push(candidate);
  }
  return kept;
}
```

*(figure: see the printed book)*

**mobile/__tests__/geometry.test.ts (excerpt)**

```
it('is 1 for identical boxes, 0 for boxes that do not touch, and exact in between',
    () => {
  const a = { x: 0, y: 0, width: 10, height: 10 };
  assert.equal(iou(a, a), 1);
  assert.equal(iou(a, { x: 20, y: 20, width: 5, height: 5 }), 0);
  assert.equal(iou(a, { x: 10, y: 0, width: 10, height: 10 }), 0); // touching
      edges only
  assert.equal(iou(a, { x: 5, y: 0, width: 10, height: 10 }), 50 / 150); // overlap
      50, union 150
});

it('keeps separate objects, and boxes with different labels do not suppress each
    other', () => {
  const result = nms([det(0, 0, 100, 100, 0.9), det(300, 300, 100, 100, 0.8),
      det(5, 5, 100, 100, 0.7, 'table')]);
  assert.deepEqual(result.map((d) => [d.label, d.score]), [['cup', 0.9], ['cup',
      0.8], ['table', 0.7]]);
});
```


### Problem 2: the boxes are right in the log and wrong on the screen

The camera frame and the view on the screen almost never have the same shape. The preview is scaled to **fill** the view (“cover”: the frame is cropped) or to **fit** inside it (“contain”: there are bars). A box found in frame coordinates must be scaled and shifted the same way before you draw it. Selfie cameras add a mirror image. Always use the size of the frame **after rotation**.

**mobile/lib/cv/geometry.ts (mapBoxToView)**

```
/**
 * Where does a box found in the CAMERA FRAME appear on the SCREEN? The preview is
     scaled to fill the view
 * ("cover": the frame is cropped) or to fit inside it ("contain": there are bars).
     Drawing an overlay
 * without this is the classic bug: the boxes are right in the logs and wrong on
     screen.
 * `frame` must be the size of the image in DISPLAY orientation (after rotation).
 */
export function mapBoxToView(box: Box, frame: Size, view: Size, fit: 'cover' |
    'contain', mirrored = false): Box {
  const scale = fit === 'cover' ? Math.max(view.width / frame.width, view.height /
      frame.height) : Math.min(view.width / frame.width, view.height /
      frame.height);
  const offsetX = (view.width - frame.width * scale) / 2;
  const offsetY = (view.height - frame.height * scale) / 2;
  const mapped = { x: box.x * scale + offsetX, y: box.y * scale + offsetY, width:
      box.width * scale, height: box.height * scale };
  return mirrored ? { ...mapped, x: view.width - (mapped.x + mapped.width) } :
      mapped; // a selfie camera is mirrored
}

/** Cut a box to the visible area; returns null when nothing of it is visible. */
export function clampBox(box: Box, view: Size): Box | null {
  const left = Math.max(0, box.x);
  const top = Math.max(0, box.y);
  const right = Math.min(view.width, box.x + box.width);
  const bottom = Math.min(view.height, box.y + box.height);
  return right > left && bottom > top ? { x: left, y: top, width: right - left,
      height: bottom - top } : null;
}
```

**mobile/__tests__/geometry.test.ts (excerpt)**

```
it('"cover" crops the frame: the same box lands off-centre', () => {
  const box = { x: 0, y: 0, width: 1000, height: 1000 };
  assert.deepEqual(mapBoxToView(box, portraitFrame, square, 'cover'), { x: 0, y:
      -200, width: 400, height: 400 });
});

it('"contain" shows the whole frame with bars at the sides', () => {
  const box = { x: 0, y: 0, width: 1000, height: 1000 };
  assert.deepEqual(mapBoxToView(box, portraitFrame, square, 'contain'), { x: 100,
      y: 0, width: 200, height: 200 });
});
```


### Problem 3: platforms disagree

The `expo-camera` documentation states that the **order of a barcode’s corner points differs between platforms**: Android and web list top-left, top-right, bottom-right, bottom-left; iOS lists bottom-left, bottom-right, top-left, top-right. Code that draws a quadrilateral around a code will twist on one platform unless you normalise the order once, at the edge.

**mobile/lib/cv/geometry.ts (orderCorners)**

```
/**
 * expo-camera lists a barcode's corners in a different order on each platform (see
     its documentation):
 * Android and web: top-left, top-right, bottom-right, bottom-left.
 * iOS: bottom-left, bottom-right, top-left, top-right.
 * Return them in ONE order (top-left, top-right, bottom-right, bottom-left) so the
     rest of the code does not care.
 */
export function orderCorners(points: Point[], platform: 'ios' | 'android' | 'web'):
    Point[] {
  if (points.length !== 4) return points; // not available for every code type
  return platform === 'ios' ? [points[2], points[3], points[1], points[0]] : points;
}
```


### Problem 4: results flicker

A code appears for one frame, vanishes, and appears again. If every sighting triggers an action you open the same link five times. The **stability check** acts only when the same value is seen in several frames in a row, then stays quiet for that value until it has left the view or a cooldown has passed.

**mobile/lib/cv/geometry.ts (StableDetector)**

```
/**
 * A detector flickers: a code appears for one frame, vanishes, appears again. Act
     only when the SAME value has
 * been seen in `framesRequired` frames in a row, and then not again for the same
     value until `cooldownMs`
 * has passed or it has left the view.
 */
export class StableDetector {
  private candidate: string | null = null;
  private seen = 0;
  private lastFired: string | null = null;
  private lastFiredAt = -Infinity;
  private emptyFrames = 0;

  constructor(
    private readonly options: { framesRequired?: number; cooldownMs?: number;
        clearAfterEmptyFrames?: number } = {},
  ) {}

  /** Call once per frame with what was seen (or null). Returns the value when it
      is time to act. */
  update(value: string | null, nowMs: number): string | null {
    const { framesRequired = 3, cooldownMs = 3000, clearAfterEmptyFrames = 5 } =
        this.options;
    if (value === null) {
      this.candidate = null;
      this.seen = 0;
      if (++this.emptyFrames >= clearAfterEmptyFrames) this.lastFired = null; // it
          left the view: allow it again
      return null;
    }
    this.emptyFrames = 0;
    this.seen = value === this.candidate ? this.seen + 1 : 1;
    this.candidate = value;
    if (this.seen < framesRequired) return null;
    if (value === this.lastFired && nowMs - this.lastFiredAt < cooldownMs) return
        null;
    this.lastFired = value;
    this.lastFiredAt = nowMs;
    return value;
  }
}
```

**mobile/__tests__/geometry.test.ts (excerpt)**

```
it('does not fire again for the same code while it stays in view, until the
    cooldown passes', () => {
  const d = new StableDetector({ framesRequired: 2, cooldownMs: 1000 });
  d.update('A', 0);
  assert.equal(d.update('A', 30), 'A');
  for (let t = 60; t < 900; t += 30) assert.equal(d.update('A', t), null);
  assert.equal(d.update('A', 1100), 'A');
});

it('a different code fires at once, cooldown or not', () => {
  const d = new StableDetector({ framesRequired: 2, cooldownMs: 60_000 });
  d.update('A', 0); assert.equal(d.update('A', 30), 'A');
  d.update('B', 60);
  assert.equal(d.update('B', 90), 'B');
});
```


## Camera and Sensor Features: QR Codes and Shake


### Scanning a QR code safely

`expo-camera` can detect QR codes without any model of your own. The camera is easy; the **content** is the danger. A QR code is text that a stranger chose, so it is untrusted input like any other (Chapter 17). It can hold a link to a fake login page, a `javascript:` or `intent:` address, a Wi-Fi password, a phone number to dial. Attackers print stickers and put them over legitimate codes.

So the scanner reports only web addresses that pass a strict check: HTTPS only, no hidden user name (`https://example.com@evil.net`), no unusual port, a plain host name, and a host that is on **your allow-list** or a subdomain of it. We parse by hand because React Native’s built-in `URL` class does not implement everything browsers do, and a security check must not depend on a half-implemented class.

**mobile/lib/cv/scan.ts**

```
export type ScanResult = { ok: true; url: string } | { ok: false; reason: string };

/**
 * A QR code is text that a stranger chose. Treat it like any other untrusted
     input: only open web addresses
 * on HTTPS that belong to a host you list, with no hidden user name and no
     surprises. (We parse by hand because
 * React Native's built-in URL class does not implement everything browsers do.)
 */
export function parseScannedUrl(data: string, allowedHosts: string[]): ScanResult {
  const text = data.trim();
  if (text.length === 0 || text.length > 2048) return { ok: false, reason: 'empty
      or too long' };
  if (/[\u0000-\u001f\u007f\s]/.test(text)) return { ok: false, reason: 'contains
      control characters or spaces' };

  const match = /^https:\/\/([^/?#]*)([/?#].*)?$/i.exec(text);
  if (!match) return { ok: false, reason: 'not an https address' };

  const authority = match[1];
  if (authority.includes('@')) return { ok: false, reason: 'contains a user name' };
  const [host, port, ...extra] = authority.toLowerCase().split(':');
  if (extra.length > 0 || (port !== undefined && port !== '443')) return { ok:
      false, reason: 'unusual port' };
  if (!/^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/.test(host
      )) return { ok: false, reason: 'not a plain host name' };

  const allowed = allowedHosts.some((h) => host === h.toLowerCase() ||
      host.endsWith(`.${h.toLowerCase()}`));
  return allowed ? { ok: true, url: text } : { ok: false, reason: 'host is not on
      the allow-list' };
}
```

**mobile/__tests__/scan.test.ts (excerpt)**

```
it('refuses look-alike and tricky hosts', () => {
  for (const bad of [
    'https://example.com.evil.net/x', 'https://notexample.com/x',
        'https://evil.net/https://example.com',
    'https://example.com@evil.net/x', 'https://user:pass@example.com/x',
        'https://example.com:8443/x',
    'https://evil.net#@example.com', 'https://127.0.0.1/x', 'https://localhost/x',
        'https://exämple.com/x',
  ]) {
    assert.equal(ok(bad), false, bad);
  }
});

it('refuses other schemes: http, javascript, file, intent, tel, sms and plain
    text', () => {
  for (const bad of ['http://example.com', 'javascript:alert(1)',
      'file:///etc/passwd', 'intent://scan#Intent;end', 'tel:+123', 'sms:+123',
      'just text', 'WIFI:S:net;P:pass;;']) {
    assert.equal(ok(bad), false, bad);
  }
});
```

The component combines the camera, the stability check and the safe parser. Even a code that passes should not open silently: show the address and ask the user to confirm, because the allow-list protects against strangers’ hosts but not against a legitimate page you did not mean to open.

**mobile/components/QrScanner.tsx**

```
interface Props {
  allowedHosts: string[];
  onUrl: (url: string) => void;
  onRejected?: (reason: string) => void;
}

/** Scans QR codes and reports only web addresses that pass `parseScannedUrl`. */
export function QrScanner({ allowedHosts, onUrl, onRejected }: Props) {
  const [permission, requestPermission] = useCameraPermissions();
  const detector = useRef(new StableDetector({ framesRequired: 3, cooldownMs: 4000
      })).current;
  const seenAny = useRef(false);

  const handle = useMemo(
    () => (result: BarcodeScanningResult) => {
      seenAny.current = true;
      const stable = detector.update(result.data, Date.now()); // act only when the
          same code is seen in 3 frames
      if (stable === null) return;
      const parsed = parseScannedUrl(stable, allowedHosts);
      if (parsed.ok) onUrl(parsed.url);
      else onRejected?.(parsed.reason);
    },
    [allowedHosts, detector, onRejected, onUrl],
  );

  if (!permission) return <View style={styles.fill} />;
  if (!permission.granted) {
    return (
      <View style={[styles.fill, styles.center]}>
        <Text style={styles.message}>We need the camera to scan codes.</Text>
        <Pressable accessibilityRole="button" onPress={() => void
            requestPermission()} style={styles.button}>
          <Text style={styles.buttonText}>Allow camera</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <CameraView
      style={styles.fill}
      facing="back"
      barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
      onBarcodeScanned={handle}
      accessibilityLabel="Camera view for scanning a QR code"
    />
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  center: { alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24 },
  message: { fontSize: 16, textAlign: 'center' },
  button: { minHeight: 44, paddingHorizontal: 20, borderRadius: 12,
      backgroundColor: '#1D4ED8', alignItems: 'center', justifyContent: 'center' },
  buttonText: { color: '#FFFFFF', fontWeight: '600' },
});
```


### Reading the accelerometer: shake to report a problem

The **accelerometer** reports how the phone is accelerating along three axes, in units of g (about 9.8 m/s squared). Two facts surprise beginners. A phone lying still reads about **1 g**, because gravity is part of the measurement, and slowly tilting the phone changes *which axes* carry the 1 g but not the total. So to detect a *shake* you look at how far the total strength moves away from 1 g.

| **Step** | **Why** |
|---|---|
| **Compute the strength** | `sqrt(x*x + y*y + z*z)`: independent of how the phone is held |
| **Look for hard movements** | A reading far from 1 g (0.8 g by default) is a hard movement |
| **Count each movement once** | One movement spans several readings; count the rising edge only |
| **Require several, close together** | Three movements within 0.7 seconds is a shake; one bump in a pocket is not |
| **Cool down** | After a shake, ignore further shakes for 1.5 seconds |
| **Smooth when needed** | A low-pass filter averages away noise: `y = y + alpha * (x - y)` |

**mobile/lib/cv/sensors.ts**

```
export interface Reading {
  x: number;
  y: number;
  z: number;
}

/** Strength of the acceleration in g. A phone lying still reads about 1 g: gravity
    is part of the measurement. */
export const magnitude = ({ x, y, z }: Reading): number => Math.sqrt(x * x + y * y
    + z * z);

/** Smooths noisy readings: each new value moves the output a fraction `alpha` of
    the way. Small alpha = smoother, slower. */
export class LowPassFilter {
  private value: number | null = null;
  constructor(private readonly alpha: number) {
    if (!(alpha > 0 && alpha <= 1)) throw new Error('alpha must be greater than 0
        and at most 1');
  }
  next(sample: number): number {
    this.value = this.value === null ? sample : this.value + this.alpha * (sample -
        this.value);
    return this.value;
  }
}

export interface ShakeOptions {
  /** How far from 1 g counts as a hard movement. */
  deltaG?: number;
  /** Hard movements needed inside the window. */
  spikesRequired?: number;
  windowMs?: number;
  cooldownMs?: number;
}

/**
 * "Shake to report a problem". A shake is several hard movements in a short time:
     one bump in a pocket is
 * not enough, and slowly tilting the phone never changes the strength of the
     acceleration at all.
 */
export class ShakeDetector {
  private spikes: number[] = [];
  private wasHard = false;
  private lastShakeAt = -Infinity;

  constructor(private readonly options: ShakeOptions = {}) {}

  /** Feed every reading with the time it was taken. Returns true at the moment a
      shake is recognised. */
  push(reading: Reading, nowMs: number): boolean {
    const { deltaG = 0.8, spikesRequired = 3, windowMs = 700, cooldownMs = 1500 } =
        this.options;
    const hard = Math.abs(magnitude(reading) - 1) >= deltaG;
    const rising = hard && !this.wasHard; // count each movement once, not every
        reading inside it
    this.wasHard = hard;
    if (!rising) return false;

    this.spikes = [...this.spikes.filter((t) => nowMs - t <= windowMs), nowMs];
    if (this.spikes.length >= spikesRequired && nowMs - this.lastShakeAt >=
        cooldownMs) {
      this.lastShakeAt = nowMs;
      this.spikes = [];
      return true;
    }
    return false;
  }
}
```

**mobile/__tests__/sensors.test.ts (excerpt)**

```
it('does not fire for a phone at rest or one that is slowly tilted', () => {
  const tilting = Array.from({ length: 60 }, (_, i) => ({ x: Math.sin(i / 10), y:
      0, z: Math.cos(i / 10) })); // always 1 g
  assert.deepEqual(shakes([...Array(40).fill(rest), ...tilting]), []);
});

it('fires on several hard movements close together', () => {
  const wiggle = [hard, rest, hard, rest, hard, rest];
  assert.deepEqual(shakes(wiggle), [200]); // the third movement completes the shake
});
```

Sensors cost battery, so the hook listens only while the screen that wants shakes is mounted, and asks for ten readings a second, which is plenty for a human movement.

**mobile/hooks/useShake.ts**

```
/**
 * Calls `onShake` when the phone is shaken. Sensors cost battery, so we listen
     only while the screen that
 * wants shakes is mounted and ask for 10 readings a second, which is plenty for a
     human movement.
 */
export function useShake(onShake: () => void, enabled = true): void {
  useEffect(() => {
    if (!enabled) return;
    let subscription: { remove: () => void } | null = null;
    let cancelled = false;
    const detector = new ShakeDetector();

    void Accelerometer.isAvailableAsync().then((available) => {
      if (!available || cancelled) return;
      Accelerometer.setUpdateInterval(100);
      subscription = Accelerometer.addListener((reading) => {
        if (detector.push(reading, Date.now())) onShake();
      });
    });
    return () => {
      cancelled = true;
      subscription?.remove();
    };
  }, [onShake, enabled]);
}
```

> **Test the logic with recorded data, tune on real phones**
>
> The detector is tested with synthetic readings, which proves the logic. The thresholds (0.8 g, three movements, 0.7 seconds) are starting points: tune them with recordings from real phones and real people, including someone walking and someone on a bus, and make sure a phone in a bag does not trigger it.


## Testing Multimodal Features

Multimodal code seems hard to test, because it involves files, tools and models. The trick used throughout this chapter is to test each layer in the way that fits it.

| **Layer** | **How we tested it** | **Example** |
|---|---|---|
| **Pure logic** | Ordinary unit tests, no files and no network | IoU, NMS, coordinate mapping, shake detection, the dictation reducer, QR safety |
| **File handling** | Generate **real** files inside the test, so there are no fixtures to maintain | Pillow makes JPEGs with GPS data; reportlab makes PDFs; ffmpeg makes audio |
| **Hostile input** | Build the attack on purpose | A 200-byte PNG claiming 1.6 billion pixels; a playlist pointing at a secret file; a text file named `.jpg` |
| **Provider calls** | A mock server with the **real SDK**, so the request shape is checked | Multipart fields of a transcription; the JSON of a speech request; every failure class |
| **Pipelines** | Real API, real task in eager mode, a **fake** provider | Upload, process, status, deletion, permission checks |
| **Model quality** | Evaluation sets (Chapter 33) | Word error rate on your users’ voices; answers about sample photos |
| **The device** | A manual matrix on real phones | Below |

| **Device scenario** | **What to check** |
|---|---|
| **Permission denied** | The message and the Open Settings button; no crash; the rest of the app works |
| **A very large photo** (50 megapixels) | It is shrunk before upload; the upload finishes; memory stays steady |
| **A photo from the camera, rotated** | It arrives upright; GPS is gone (check the stored copy) |
| **A long recording** | Stops at 60 seconds by itself; the timer is honest |
| **A phone call during recording** | The recorder stops; no crash; a clear message |
| **A Bluetooth headset** | Recording and playback both work and switch cleanly |
| **Airplane mode in the middle of an upload** | A calm error and a way to try again; no duplicate attachment |
| **A noisy place** | The transcript is reviewable; “no speech found” is not shown for real speech |
| **A QR code with a bad link** | It is refused with a reason; nothing opens |
| **Leaving the screen while speaking or recording** | Sound stops; the recorder is released; no leak |
