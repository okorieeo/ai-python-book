"""Splitting documents into chunks that can be embedded, searched and cited.

Every strategy keeps one promise: chunk.text == source[chunk.start:chunk.end]. That lets the
UI highlight the exact passage a citation points to.
"""
import re
from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    """Rough token count (about 4 characters per token in English). Good enough for budgets."""
    return (len(text) + 3) // 4 if text else 0


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    start: int            # character offsets in the cleaned source text
    end: int
    heading_path: tuple = ()

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


def _trim(text: str, start: int, end: int):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _windows(text: str, start: int, end: int, size: int, overlap: int) -> list:
    """Cut text[start:end] into windows of about `size` characters, on word boundaries."""
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError("size must be at least 1 and overlap must be smaller than size")
    spans, pos = [], start
    while pos < end:
        cut = min(pos + size, end)
        if cut < end:
            space = max(text.rfind(" ", pos + size // 2, cut), text.rfind("\n", pos + size // 2, cut))
            if space > pos:
                cut = space
        s, e = _trim(text, pos, cut)
        if e > s:
            spans.append((s, e))
        if cut >= end:
            break
        nxt = max(cut - overlap, pos + 1)
        while nxt < cut and not text[nxt - 1].isspace():   # start the next window on a word
            nxt += 1
        pos = nxt
    return spans


def _to_chunks(text: str, spans: list, heading_path: tuple = ()) -> list:
    return [Chunk(i, text[s:e], s, e, heading_path) for i, (s, e) in enumerate(spans)]


def fixed_size_chunks(text: str, size: int = 800, overlap: int = 100) -> list:
    """Windows of about `size` characters that overlap by `overlap`. Simple and predictable."""
    return _to_chunks(text, _windows(text, 0, len(text), size, overlap))


_BLANK_LINE = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _paragraph_spans(text: str, start: int, end: int) -> list:
    spans, pos = [], start
    for match in _BLANK_LINE.finditer(text, start, end):
        s, e = _trim(text, pos, match.start())
        if e > s:
            spans.append((s, e))
        pos = match.end()
    s, e = _trim(text, pos, end)
    if e > s:
        spans.append((s, e))
    return spans


def _sentence_spans(text: str, start: int, end: int) -> list:
    spans, pos = [], start
    for match in _SENTENCE_END.finditer(text, start, end):
        s, e = _trim(text, pos, match.start())
        if e > s:
            spans.append((s, e))
        pos = match.end()
    s, e = _trim(text, pos, end)
    if e > s:
        spans.append((s, e))
    return spans


def _pack(text: str, pieces: list, max_chars: int, split_long) -> list:
    """Greedily join neighbouring pieces up to max_chars. Oversized pieces are split further."""
    spans, cur_s, cur_e = [], None, None

    def flush():
        nonlocal cur_s, cur_e
        if cur_s is not None:
            spans.append((cur_s, cur_e))
        cur_s = cur_e = None

    for s, e in pieces:
        if e - s > max_chars:
            flush()
            spans.extend(split_long(s, e))
        elif cur_s is not None and e - cur_s > max_chars:
            flush()
            cur_s, cur_e = s, e
        elif cur_s is None:
            cur_s, cur_e = s, e
        else:
            cur_e = e
    flush()
    return spans


def _recursive_spans(text: str, start: int, end: int, max_chars: int) -> list:
    """Paragraphs first, then sentences, then plain windows: the most natural boundary that fits."""
    def split_paragraph(s, e):
        return _pack(text, _sentence_spans(text, s, e), max_chars,
                     lambda a, b: _windows(text, a, b, max_chars, 0))
    return _pack(text, _paragraph_spans(text, start, end), max_chars, split_paragraph)


def paragraph_chunks(text: str, max_chars: int = 1000) -> list:
    """Keep paragraphs together; split long ones at sentences, then at words."""
    return _to_chunks(text, _recursive_spans(text, 0, len(text), max_chars))


_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.M)


def markdown_chunks(text: str, max_chars: int = 1000) -> list:
    """Split at Markdown headings, then paragraphs. Each chunk records the headings above it.

    A heading always stays with the text below it, so a chunk can be longer than max_chars by the
    length of its heading.
    """
    marks = [(m.start(), len(m.group(1)), m.group(2)) for m in _HEADING.finditer(text)]
    sections, stack = [], []
    first = marks[0][0] if marks else len(text)
    if first > 0:
        sections.append((0, first, ()))
    for i, (pos, level, title) in enumerate(marks):
        stack = [(lv, t) for lv, t in stack if lv < level] + [(level, title)]
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        sections.append((pos, stop, tuple(t for _, t in stack)))
    # A heading with no text of its own ("# Guide" directly followed by "## Setup") would become a
    # useless chunk that matches searches and answers nothing. Join it to the section after it.
    merged, carry = [], None
    for s, e, path in sections:
        s = carry if carry is not None else s
        carry = None
        has_body = any(not line.lstrip().startswith("#") for line in text[s:e].splitlines() if line.strip())
        if not has_body and (s, e, path) != sections[-1]:
            carry = s
            continue
        merged.append((s, e, path))
    chunks = []
    for s, e, path in merged:
        spans = _recursive_spans(text, s, e, max_chars)
        # A heading followed by an oversized paragraph is cut off from it by the packer. Put it back
        # with the first piece of text; the chunk may then exceed max_chars by the length of the heading.
        if len(spans) > 1 and all(not l.strip() or l.lstrip().startswith("#") for l in text[spans[0][0]:spans[0][1]].splitlines()):
            spans = [(spans[0][0], spans[1][1])] + spans[2:]
        for cs, ce in spans:
            chunks.append(Chunk(len(chunks), text[cs:ce], cs, ce, path))
    return chunks


def chunk_stats(chunks: list) -> dict:
    """Count and size summary, handy for checking a chunker on your own documents."""
    sizes = [c.tokens for c in chunks]
    return {
        "chunks": len(chunks),
        "avg_tokens": round(sum(sizes) / len(sizes), 1) if sizes else 0,
        "max_tokens": max(sizes) if sizes else 0,
        "min_tokens": min(sizes) if sizes else 0,
    }
