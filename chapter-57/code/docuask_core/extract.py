"""Turn an uploaded file into a list of Pages, or fail with a message that is safe to show the user.

Security rules applied here (section 57.5 and 57.15):
- never trust the file name or the Content-Type header: check the first bytes ("magic bytes");
- cap pages, characters and decompressed size (zip bombs);
- refuse encrypted and image-only files with a clear explanation instead of silently indexing nothing.
"""
import io
import re
import zipfile
from typing import List

from .chunking import Page
from .text import normalize_text


class ExtractionError(Exception):
    """The message is written for the end user and is safe to display."""


class NoTextError(ExtractionError):
    pass


SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")


def sniff_type(data: bytes, filename: str) -> str:
    name = filename.lower()
    if data.startswith(b"%PDF-"):
        kind = "pdf"
    elif data.startswith(b"PK\x03\x04") and name.endswith(".docx"):
        kind = "docx"
    elif name.endswith((".txt", ".md")) and b"\x00" not in data[:4096]:
        kind = "text"
    else:
        raise ExtractionError("This file type is not supported. Upload a PDF, Word (.docx), .txt or .md file.")
    if (kind == "pdf" and not name.endswith(".pdf")) or (kind == "docx" and not name.endswith(".docx")):
        raise ExtractionError("The file extension does not match the file contents.")
    return kind


def _pdf_pages(data: bytes, max_pages: int) -> List[Page]:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                ok = reader.decrypt("")
            except Exception:
                ok = 0
            if not ok:
                raise ExtractionError("This PDF is password protected. Remove the password and upload it again.")
        count = len(reader.pages)
        if count > max_pages:
            raise ExtractionError(f"This PDF has {count} pages; the limit is {max_pages}.")
        pages = [Page(i + 1, normalize_text(p.extract_text() or "")) for i, p in enumerate(reader.pages)]
    except ExtractionError:
        raise
    except (PyPdfError, ValueError, KeyError, OSError, RecursionError):
        raise ExtractionError("This PDF could not be read. It may be damaged; try printing it to a new PDF.")
    with_text = sum(1 for p in pages if len(p.text) >= 20)
    if with_text == 0:
        raise NoTextError("This PDF has no selectable text (it looks like a scan). Run OCR on it first, then upload it again.")
    return pages


def _docx_pages(data: bytes, max_uncompressed: int, max_chars: int) -> List[Page]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if sum(i.file_size for i in zf.infolist()) > max_uncompressed:
                raise ExtractionError("This Word file expands to an unreasonable size and was rejected.")
            if "word/document.xml" not in zf.namelist():
                raise ExtractionError("This does not look like a Word document.")
    except zipfile.BadZipFile:
        raise ExtractionError("This Word file is damaged.")
    from docx import Document
    try:
        doc = Document(io.BytesIO(data))
    except Exception:
        raise ExtractionError("This Word file could not be read.")
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    text = normalize_text("\n\n".join(parts))
    if len(text) > max_chars:
        raise ExtractionError("This document has more text than the limit allows.")
    if not text:
        raise NoTextError("This Word file contains no text.")
    return [Page(None, text)]


def _text_pages(data: bytes, max_chars: int) -> List[Page]:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ExtractionError("This text file is not in a readable encoding.")
    if len(text) > max_chars:
        raise ExtractionError("This file has more text than the limit allows.")
    # A form feed (\f) is the classic "new page" character, so plain-text files can carry page numbers.
    raw_pages = text.split("\f") if "\f" in text else [text]
    pages = [Page(i + 1 if len(raw_pages) > 1 else None, normalize_text(t)) for i, t in enumerate(raw_pages)]
    pages = [p for p in pages if p.text]
    if not pages:
        raise NoTextError("This file is empty.")
    return pages


def extract_pages(data: bytes, filename: str, max_pages: int = 500, max_chars: int = 5_000_000,
                  max_uncompressed: int = 100 * 1024 * 1024) -> List[Page]:
    kind = sniff_type(data, filename)
    if kind == "pdf":
        pages = _pdf_pages(data, max_pages)
    elif kind == "docx":
        pages = _docx_pages(data, max_uncompressed, max_chars)
    else:
        pages = _text_pages(data, max_chars)
    if sum(len(p.text) for p in pages) > max_chars:
        raise ExtractionError("This document has more text than the limit allows.")
    return pages
