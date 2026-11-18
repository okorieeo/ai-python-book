import subprocess
import tempfile
import wave
from pathlib import Path

from django.test import SimpleTestCase

from attachments.audio import probe_audio, to_speech_wav
from attachments.errors import MediaRejected
from attachments.limits import MediaLimits


def make_audio(path: Path, *extra: str, seconds: float = 2.0) -> Path:
    """Synthesise real test files with ffmpeg: a sine tone, optionally with a video track."""
    args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    if path.suffix in (".mp4",):
        args += ["-f", "lavfi", "-i", f"testsrc=size=64x64:rate=5:duration={seconds}"]
    subprocess.run([*args, *extra, str(path)], check=True, capture_output=True)
    return path


class AudioTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_probe_reads_duration_and_format_of_an_m4a(self):
        info = probe_audio(make_audio(self.dir / "a.m4a", "-c:a", "aac"))
        self.assertAlmostEqual(info.duration, 2.0, delta=0.2)
        self.assertEqual(info.codec, "aac")
        self.assertFalse(info.has_video)

    def test_a_video_file_is_noticed_and_only_its_sound_is_kept(self):
        mp4 = make_audio(self.dir / "clip.mp4", "-c:a", "aac", "-c:v", "mpeg4", "-shortest")
        self.assertTrue(probe_audio(mp4).has_video)
        out = self.dir / "out.wav"
        to_speech_wav(mp4, out, max_seconds=60)
        with wave.open(str(out)) as wav:  # a plain WAV file, so there is no video in it
            self.assertEqual((wav.getnchannels(), wav.getframerate()), (1, 16000))

    def test_conversion_makes_mono_16k_wav(self):
        src = make_audio(self.dir / "stereo.mp3", "-ac", "2", "-ar", "44100", "-c:a", "libmp3lame")
        out = self.dir / "speech.wav"
        to_speech_wav(src, out, max_seconds=60)
        with wave.open(str(out)) as wav:
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getframerate(), 16000)
            self.assertAlmostEqual(wav.getnframes() / 16000, 2.0, delta=0.2)

    def test_conversion_never_writes_more_than_the_limit(self):
        src = make_audio(self.dir / "long.wav", seconds=5)
        out = self.dir / "short.wav"
        to_speech_wav(src, out, max_seconds=2)
        with wave.open(str(out)) as wav:
            self.assertLessEqual(wav.getnframes() / 16000, 2.05)

    def test_audio_longer_than_the_limit_is_refused(self):
        src = make_audio(self.dir / "five.wav", seconds=5)
        with self.assertRaises(MediaRejected) as ctx:
            probe_audio(src, MediaLimits(max_audio_seconds=3))
        self.assertEqual(ctx.exception.code, "audio_too_long")

    def test_a_dictation_limit_can_be_stricter_than_the_general_one(self):
        src = make_audio(self.dir / "ten.wav", seconds=3)
        with self.assertRaises(MediaRejected):
            probe_audio(src, max_seconds=2)

    def test_garbage_named_like_audio_is_refused(self):
        fake = self.dir / "voice.m4a"
        fake.write_bytes(b"This is a text file pretending to be a voice note." * 20)
        with self.assertRaises(MediaRejected) as ctx:
            probe_audio(fake)
        self.assertEqual(ctx.exception.code, "unreadable_audio")
        with self.assertRaises(MediaRejected):
            to_speech_wav(fake, self.dir / "x.wav", max_seconds=10)

    def test_a_playlist_that_points_at_another_file_is_not_followed(self):
        secret = self.dir / "secret.txt"
        secret.write_text("top secret")
        playlist = self.dir / "list.m3u8"
        playlist.write_text(f"#EXTM3U\n#EXTINF:1,\n{secret}\n")
        with self.assertRaises(MediaRejected):
            probe_audio(playlist)

    def test_a_video_without_sound_is_refused(self):
        silent = self.dir / "silent.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=1",
                        "-c:v", "mpeg4", str(silent)], check=True, capture_output=True)
        with self.assertRaises(MediaRejected) as ctx:
            probe_audio(silent)
        self.assertEqual(ctx.exception.code, "unreadable_audio")
