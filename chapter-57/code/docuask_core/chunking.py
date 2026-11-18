"""Split pages of text into chunks that are good to embed AND good to cite.

Design choices (see section 57.7):
- a chunk never crosses a page boundary, so every citation has an exact page number;
- chunks end at sentence boundaries, so a cited passage reads like a quotation, not a fragment;
- neighbouring chunks overlap by a sentence, so an answer that straddles a boundary is still retrievable.
"""
import hashlib
import re
from dataclasses import dataclass
from typing import List, Optional

from .text import estimate_tokens, normalize_text

_SENT = re.compile(r'(?<=[.!?])["\')\]]*\s+(?=["\'(\[]*[A-Z0-9])')


@dataclass(frozen=True)
class Page:
    number: Optional[int]   # 1-based, or None when the format has no pages (Word, plain text)
    text: str


@dataclass(frozen=True)
class Chunk:
    index: int
    page_start: Optional[int]
    page_end: Optional[int]
    text: str
    tokens: int
    sha256: str


def split_sentences(paragraph: str) -> List[str]:
    parts = [s.strip() for s in _SENT.split(paragraph) if s.strip()]
    return parts or ([paragraph.strip()] if paragraph.strip() else [])


def _hard_split(sentence: str, max_tokens: int) -> List[str]:
    """A "sentence" longer than the limit (a table row, a run-on list) is cut at word boundaries."""
    words, out, cur = sentence.split(), [], []
    for w in words:
        if cur and estimate_tokens(" ".join(cur + [w])) > max_tokens:
            out.append(" ".join(cur))
            cur = []
        cur.append(w)
    if cur:
        out.append(" ".join(cur))
    return out


def _units(page_text: str, max_tokens: int) -> List[str]:
    units: List[str] = []
    for para in normalize_text(page_text).split("\n\n"):
        for sent in split_sentences(para):
            units.extend([sent] if estimate_tokens(sent) <= max_tokens else _hard_split(sent, max_tokens))
    return units


def chunk_pages(pages: List[Page], target_tokens: int = 300, max_tokens: int = 450,
                overlap_sentences: int = 1, min_tokens: int = 40) -> List[Chunk]:
    if not (0 < min_tokens <= target_tokens <= max_tokens):
        raise ValueError("need 0 < min_tokens <= target_tokens <= max_tokens")
    drafts: List[tuple] = []          # (page_number, [sentences])
    for page in pages:
        units = _units(page.text, max_tokens)
        current: List[str] = []
        fresh = 0                      # sentences added since the last emit (excluding carried overlap)
        for unit in units:
            candidate = " ".join(current + [unit])
            if current and fresh and estimate_tokens(candidate) > target_tokens:
                drafts.append((page.number, current))
                current = current[-overlap_sentences:] if overlap_sentences else []
                fresh = 0
                # the carried overlap must not push a single new sentence over the hard limit
                while current and estimate_tokens(" ".join(current + [unit])) > max_tokens:
                    current = current[1:]
            current.append(unit)
            fresh += 1
        if current and fresh:
            drafts.append((page.number, current))

    # a tiny last chunk of a page is merged into the previous chunk of the same page when it fits
    merged: List[tuple] = []
    for number, sents in drafts:
        text = " ".join(sents)
        if merged and merged[-1][0] == number and estimate_tokens(text) < min_tokens:
            prev_sents = merged[-1][1]
            new_text = " ".join(prev_sents + [s for s in sents if s not in prev_sents])
            if estimate_tokens(new_text) <= max_tokens:
                merged[-1] = (number, prev_sents + [s for s in sents if s not in prev_sents])
                continue
        merged.append((number, sents))

    chunks = []
    for i, (number, sents) in enumerate(merged):
        text = " ".join(sents)
        chunks.append(Chunk(i, number, number, text, estimate_tokens(text), hashlib.sha256(text.encode()).hexdigest()))
    return chunks
