import io

from django.test import SimpleTestCase
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from attachments.documents import inspect_pdf, select_pages
from attachments.errors import MediaRejected
from attachments.limits import MediaLimits


def text_pdf(pages=3):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for n in range(1, pages + 1):
        c.drawString(72, 720, f"Page {n}: the quarterly report says revenue grew in every region this year.")
        c.showPage()
    c.save()
    return buf.getvalue()


def scanned_pdf(pages=2):
    """Pages that are only a picture: what a phone scan produces."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    picture = Image.new("RGB", (300, 400), (240, 240, 240))
    for _ in range(pages):
        c.drawImage(ImageReader(picture), 50, 200, width=300, height=400)
        c.showPage()
    c.save()
    return buf.getvalue()


class InspectPdfTests(SimpleTestCase):
    def test_a_text_pdf_reports_pages_and_text(self):
        info = inspect_pdf(text_pdf(3))
        self.assertEqual(info.pages, 3)
        self.assertEqual(info.pages_with_text, 3)
        self.assertGreater(info.text_chars, 150)
        self.assertFalse(info.looks_scanned)

    def test_a_scan_has_no_text_and_is_flagged(self):
        info = inspect_pdf(scanned_pdf(2))
        self.assertEqual(info.pages, 2)
        self.assertEqual(info.text_chars, 0)
        self.assertTrue(info.looks_scanned)

    def test_too_many_pages_is_refused(self):
        with self.assertRaises(MediaRejected) as ctx:
            inspect_pdf(text_pdf(6), MediaLimits(max_pdf_pages=5))
        self.assertEqual(ctx.exception.code, "pdf_too_many_pages")

    def test_password_protected_pdfs_are_refused(self):
        writer = PdfWriter()
        for page in PdfReader(io.BytesIO(text_pdf(1))).pages:
            writer.add_page(page)
        writer.encrypt("secret")
        buf = io.BytesIO(); writer.write(buf)
        with self.assertRaises(MediaRejected) as ctx:
            inspect_pdf(buf.getvalue())
        self.assertEqual(ctx.exception.code, "pdf_encrypted")

    def test_damaged_and_fake_pdfs_are_refused(self):
        good = text_pdf(2)
        for bad in (b"%PDF-1.4\nthis is not really a pdf", good[: len(good) // 3], b"%PDF-"):
            with self.assertRaises(MediaRejected) as ctx:
                inspect_pdf(bad)
            self.assertEqual(ctx.exception.code, "unreadable_pdf")

    def test_a_long_document_is_only_sampled(self):
        info = inspect_pdf(text_pdf(40))  # 20 pages are examined, the totals are scaled up
        self.assertEqual(info.pages, 40)
        self.assertEqual(info.pages_with_text, 40)


class SelectPagesTests(SimpleTestCase):
    def test_only_the_chosen_pages_are_kept(self):
        out = select_pages(text_pdf(5), 2, 3)
        reader = PdfReader(io.BytesIO(out))
        self.assertEqual(len(reader.pages), 2)
        self.assertIn("Page 2", reader.pages[0].extract_text())
        self.assertIn("Page 3", reader.pages[1].extract_text())

    def test_bad_ranges_are_refused(self):
        for first, last in ((0, 1), (3, 2), (1, 9)):
            with self.assertRaises(MediaRejected) as ctx:
                select_pages(text_pdf(5), first, last)
            self.assertEqual(ctx.exception.code, "bad_page_range")
