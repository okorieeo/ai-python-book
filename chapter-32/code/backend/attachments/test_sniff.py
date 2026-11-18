import io

from django.test import SimpleTestCase
from PIL import Image

from attachments.sniff import is_heic, safe_filename, sniff


def _png():
    buf = io.BytesIO(); Image.new("RGB", (2, 2)).save(buf, "PNG"); return buf.getvalue()


def _jpeg():
    buf = io.BytesIO(); Image.new("RGB", (2, 2)).save(buf, "JPEG"); return buf.getvalue()


class SniffTests(SimpleTestCase):
    def test_real_images_and_pdfs_are_recognised_by_their_bytes(self):
        self.assertEqual(sniff(_png()[:32]).mime, "image/png")
        self.assertEqual(sniff(_jpeg()[:32]).mime, "image/jpeg")
        self.assertEqual(sniff(b"GIF89a" + b"\0" * 20).mime, "image/gif")
        self.assertEqual(sniff(b"RIFF\x24\0\0\0WEBPVP8 ").mime, "image/webp")
        self.assertEqual(sniff(b"%PDF-1.7\n").kind, "document")

    def test_audio_containers(self):
        self.assertEqual(sniff(b"RIFF\x24\0\0\0WAVEfmt ").mime, "audio/wav")
        self.assertEqual(sniff(b"ID3\x04\0\0\0\0\0\0").mime, "audio/mpeg")
        self.assertEqual(sniff(b"\xff\xfb\x90\x00" + b"\0" * 10).mime, "audio/mpeg")
        self.assertEqual(sniff(b"OggS\0\x02").mime, "audio/ogg")
        self.assertEqual(sniff(b"fLaC\0\0\0\x22").mime, "audio/flac")
        self.assertEqual(sniff(b"\x1a\x45\xdf\xa3\x9f").mime, "audio/webm")
        self.assertEqual(sniff(b"\0\0\0\x20ftypM4A \0\0\0\0").mime, "audio/mp4")

    def test_what_a_file_claims_to_be_does_not_matter(self):
        # an HTML page, a script and a text file: none start with a known signature
        for payload in (b"<html><script>alert(1)</script>", b"#!/bin/sh\nrm -rf /", b"just some text", b"", b"MZ\x90\x00"):
            self.assertIsNone(sniff(payload))

    def test_a_pdf_with_junk_in_front_is_refused_on_purpose(self):
        self.assertIsNone(sniff(b"GARBAGE%PDF-1.4"))

    def test_iphone_heic_is_recognised_so_we_can_explain_it(self):
        head = b"\0\0\0\x18ftypheic\0\0\0\0"
        self.assertTrue(is_heic(head))
        self.assertIsNone(sniff(head))  # not accepted, but with a clear reason available

    def test_file_names_are_reduced_to_a_harmless_label(self):
        self.assertEqual(safe_filename("../../etc/passwd"), "passwd")
        self.assertEqual(safe_filename("C:\\Users\\ada\\holiday.jpg"), "holiday.jpg")
        self.assertEqual(safe_filename("a\x00b\nc.png"), "abc.png")
        self.assertEqual(safe_filename("..."), "upload")
        self.assertEqual(safe_filename(None), "upload")
        self.assertEqual(len(safe_filename("x" * 500 + ".png")), 100)
