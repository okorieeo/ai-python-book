"""The ingestion pipeline: clean, chunk, (contextualize), embed and store one document."""
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable, Optional

from prompts.injection import risk_level, scan_for_injection

from .chunking import markdown_chunks
from .embeddings import EmbeddingError, batched
from .store import ChunkRecord


class IngestError(ValueError):
    """The document cannot be ingested (no text, unsupported type, too large). Do not retry."""


class _TextExtractor(HTMLParser):
    _BLOCKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"}

    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._skip += 1
        elif tag in self._BLOCKS:
            self.parts.append("\n\n" if tag.startswith("h") or tag == "p" else "\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1
        elif tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def extract_text(data: bytes, content_type: str) -> str:
    """Turn uploaded bytes into text. PDFs and images need extra tools (Chapter 32)."""
    base = content_type.split(";")[0].strip().lower()
    if base in {"text/plain", "text/markdown", "text/x-markdown"}:
        return data.decode("utf-8", errors="replace")
    if base in {"text/html", "application/xhtml+xml"}:
        parser = _TextExtractor()
        parser.feed(data.decode("utf-8", errors="replace"))
        return "".join(parser.parts)
    raise IngestError(f"Unsupported content type: {base or 'unknown'}")


def clean_document_text(text: str) -> str:
    """Normalize line endings and Unicode, drop control characters, collapse long blank runs."""
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cc" or ch in "\t\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclass
class IngestReport:
    doc_id: str
    status: str            # "ingested" or "unchanged"
    chunks: int = 0
    flagged: int = 0       # chunks with an injection warning
    embedded_tokens: int = 0


def document_hash(text: str, model: str, chunker_name: str) -> str:
    """Changes when the text, the embedding model or the chunking changes: any of them needs a re-index."""
    return hashlib.sha256(f"{model}\n{chunker_name}\n{text}".encode("utf-8")).hexdigest()


def ingest_document(*, doc_id: str, owner_id: str, title: str, text: str, embedder, store,
                    chunker: Callable = markdown_chunks, chunker_name: str = "markdown-1000",
                    contextualizer: Optional[Callable] = None, batch_size: int = 64,
                    max_chars: int = 2_000_000) -> IngestReport:
    """Ingest one document. Safe to run again: unchanged documents are skipped.

    contextualizer(document_text, chunk) -> str adds a short situating sentence to each chunk
    before it is embedded (section 31.6). If it fails for a chunk, that chunk is stored without it.
    """
    text = clean_document_text(text)
    if not text:
        raise IngestError("The document has no text.")
    if len(text) > max_chars:
        raise IngestError(f"The document is longer than {max_chars} characters.")

    fingerprint = document_hash(text, embedder.model, chunker_name)
    if store.document_hash(doc_id) == fingerprint:
        return IngestReport(doc_id, "unchanged")

    chunks = chunker(text)
    if not chunks:
        raise IngestError("The document produced no chunks.")

    contexts = []
    for chunk in chunks:
        try:
            contexts.append((contextualizer(text, chunk) if contextualizer else "").strip())
        except Exception:
            contexts.append("")

    inputs = [(f"{ctx}\n\n{c.text}" if ctx else c.text) for c, ctx in zip(chunks, contexts)]
    vectors = []
    for batch in batched(inputs, batch_size):
        vectors.extend(embedder.embed_documents(batch))
    if len(vectors) != len(chunks) or any(len(v) != embedder.dimensions for v in vectors):
        raise EmbeddingError("The embedder returned the wrong number or size of vectors.")

    records, flagged = [], 0
    for chunk, ctx, vector in zip(chunks, contexts, vectors):
        risk = risk_level(scan_for_injection(chunk.text))
        flagged += risk != "none"
        records.append(ChunkRecord(
            doc_id=doc_id, owner_id=owner_id, index=chunk.index, title=title, text=chunk.text,
            start=chunk.start, end=chunk.end, heading_path=chunk.heading_path, context=ctx,
            embedding=vector, embedding_model=embedder.model, injection_risk=risk,
        ))
    store.replace_document(doc_id, fingerprint, records)
    return IngestReport(doc_id, "ingested", len(records), flagged, sum(len(i) + 3 for i in inputs) // 4)
