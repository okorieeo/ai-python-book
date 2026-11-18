import io
import struct
import zlib

from django.test import SimpleTestCase
from PIL import Image

from attachments.errors import MediaRejected
from attachments.images import normalize_image
from attachments.limits import MediaLimits
from attachments.vision_math import count_image_tokens


def jpeg_bytes(size=(200, 100), color=(200, 30, 30), exif=None, mode="RGB", quality=90):
    buf = io.BytesIO()
    Image.new(mode, size, color if mode == "RGB" else 0).save(buf, "JPEG", quality=quality, **({"exif": exif} if exif else {}))
    return buf.getvalue()


def png_claiming_size(width, height):
    """A tiny, valid-looking PNG whose header CLAIMS a huge size: the classic decompression bomb."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\0")) + chunk(b"IEND", b"")


class NormalizeImageTests(SimpleTestCase):
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
        exif[0x8825] = {1: "N", 2: (6.0, 27.0, 0.0), 3: "E", 4: (3.0, 23.0, 0.0)}  # GPS IFD
        original = jpeg_bytes(exif=exif.tobytes())
        self.assertTrue(Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825), "test setup: GPS must be present")

        out = normalize_image(original)
        cleaned = Image.open(io.BytesIO(out.data))
        self.assertEqual(dict(cleaned.getexif()), {})
        self.assertNotIn(b"Acme", out.data)
        self.assertNotIn(b"Exif", out.data[:64])

    def test_the_cameras_rotation_is_applied_to_the_pixels(self):
        exif = Image.Exif(); exif[0x0112] = 6  # "rotate 90 degrees clockwise to display"
        out = normalize_image(jpeg_bytes(size=(200, 100), exif=exif.tobytes()))
        self.assertEqual((out.width, out.height), (100, 200))

    def test_big_photos_shrink_to_what_the_model_can_use(self):
        out = normalize_image(jpeg_bytes(size=(6000, 4000)))
        self.assertTrue(out.resized)
        self.assertLessEqual(max(out.width, out.height), 1568)
        self.assertLessEqual(out.visual_tokens, 1568)
        self.assertEqual(out.visual_tokens, count_image_tokens(out.width, out.height))
        self.assertEqual((out.original_width, out.original_height), (6000, 4000))
        self.assertEqual(out.mime, "image/jpeg")

    def test_small_pictures_are_not_enlarged(self):
        out = normalize_image(jpeg_bytes(size=(300, 200)))
        self.assertEqual((out.width, out.height), (300, 200))
        self.assertFalse(out.resized)

    def test_transparency_is_kept_as_png(self):
        buf = io.BytesIO(); Image.new("RGBA", (50, 50), (255, 0, 0, 90)).save(buf, "PNG")
        out = normalize_image(buf.getvalue())
        self.assertEqual(out.mime, "image/png")
        self.assertEqual(Image.open(io.BytesIO(out.data)).mode, "RGBA")

    def test_an_animation_becomes_its_first_frame(self):
        frames = [Image.new("RGB", (40, 40), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
        buf = io.BytesIO(); frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=50, loop=0)
        out = normalize_image(buf.getvalue())
        self.assertEqual(getattr(Image.open(io.BytesIO(out.data)), "n_frames", 1), 1)
        r, g, b = Image.open(io.BytesIO(out.data)).convert("RGB").getpixel((5, 5))
        self.assertGreater(r, 200)

    def test_cmyk_photos_come_out_as_ordinary_rgb(self):
        buf = io.BytesIO(); Image.new("CMYK", (60, 60), (0, 255, 255, 0)).save(buf, "JPEG")
        out = normalize_image(buf.getvalue())
        self.assertEqual(Image.open(io.BytesIO(out.data)).mode, "RGB")

    def test_damaged_and_fake_pictures_are_refused(self):
        good = jpeg_bytes(size=(400, 300))
        for bad in (good[: len(good) // 2], b"not an image at all", b"\xff\xd8\xff garbage", b""):
            with self.assertRaises(MediaRejected) as ctx:
                normalize_image(bad)
            self.assertEqual(ctx.exception.code, "unreadable_image")

    def test_the_output_is_squeezed_to_the_byte_budget(self):
        import random
        rnd = random.Random(1)
        noise = Image.frombytes("RGB", (1200, 900), bytes(rnd.getrandbits(8) for _ in range(1200 * 900 * 3)))
        buf = io.BytesIO(); noise.save(buf, "JPEG", quality=95)
        out = normalize_image(buf.getvalue(), MediaLimits(max_output_image_bytes=250_000))
        self.assertLessEqual(len(out.data), 250_000)

    def test_the_checksum_describes_the_cleaned_bytes(self):
        import hashlib
        out = normalize_image(jpeg_bytes())
        self.assertEqual(out.sha256, hashlib.sha256(out.data).hexdigest())
