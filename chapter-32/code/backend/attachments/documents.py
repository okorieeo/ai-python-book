import io
from dataclasses import dataclass

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError

from .errors import MediaRejected
from .limits import MediaLimits, get_limits

MIN_CHARS_PER_PAGE = 20  # fewer characters than this on a page usually means a scan or a picture


@dataclass(frozen=True)
class PdfInfo:
    pages: int
    pages_with_text: int
    text_chars: int

    @property
    def looks_scanned(self) -> bool:
        """Mostly pictures of pages. Fine for a vision model, useless for plain text extraction."""
        return self.pages > 0 and self.pages_with_text < max(1, self.pages // 2)


def _open(data: bytes) -> PdfReader:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise MediaRejected("pdf_encrypted", "Password-protected PDFs are not supported.")
        len(reader.pages)  # forces the page tree to be read, so a damaged file fails here and not later
        return reader
    except MediaRejected:
        raise
    except (PyPdfError, ValueError, KeyError, RecursionError, OSError, TypeError, AttributeError):
        raise MediaRejected("unreadable_pdf", "The PDF could not be read.") from None


def inspect_pdf(data: bytes, limits: MediaLimits | None = None) -> PdfInfo:
    """Count pages and check for text, without sending anything to a model."""
    limits = limits or get_limits()
    reader = _open(data)
    pages = len(reader.pages)
    if pages == 0:
        raise MediaRejected("unreadable_pdf", "The PDF has no pages.")
    if pages > limits.max_pdf_pages:
        raise MediaRejected("pdf_too_many_pages", f"The PDF has more than {limits.max_pdf_pages} pages.")

    chars = with_text = 0
    for page in reader.pages[: min(pages, 20)]:  # a sample is enough to tell text from scans
        try:
            n = len((page.extract_text() or "").strip())
        except Exception:  # extraction can fail on odd fonts; that page just counts as "no text"
            n = 0
        chars += n
        with_text += n >= MIN_CHARS_PER_PAGE
    sampled = min(pages, 20)
    scale = pages / sampled
    return PdfInfo(pages=pages, pages_with_text=round(with_text * scale), text_chars=round(chars * scale))


def select_pages(data: bytes, first: int, last: int) -> bytes:
    """A new PDF with only pages first..last (1-based, inclusive). Sending 5 pages costs 5 pages, not 80."""
    reader = _open(data)
    total = len(reader.pages)
    if not (1 <= first <= last <= total):
        raise MediaRejected("bad_page_range", f"Choose pages between 1 and {total}.")
    writer = PdfWriter()
    for index in range(first - 1, last):
        writer.add_page(reader.pages[index])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
