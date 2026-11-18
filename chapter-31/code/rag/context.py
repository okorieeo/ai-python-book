"""Turning retrieved chunks into the sources block that goes into the prompt."""
import re
from dataclasses import dataclass

from prompts.blocks import escape_tags, xml_block


@dataclass
class SourceRef:
    id: str          # "S1", "S2", ...
    record: object   # the ChunkRecord


@dataclass
class SourceBundle:
    text: str        # the finished block for the prompt
    sources: list    # [SourceRef] in the order they appear

    def get(self, source_id: str):
        return next((s for s in self.sources if s.id == source_id), None)


def _attr(value: str, limit: int = 100) -> str:
    """Make a value safe inside a tag attribute: no quotes, angle brackets or line breaks."""
    return re.sub(r'["<>\r\n]+', " ", value).strip()[:limit]


def build_sources(hits: list, *, max_chars: int = 12000) -> SourceBundle:
    """Number the chunks S1, S2, ... and wrap them as untrusted data.

    Each chunk's text is escaped (so it cannot close the wrapper or fake a <source> tag) and the
    whole block is wrapped in <untrusted_data>. Chunks are added best first until max_chars is
    reached, so the prompt never grows without limit.
    """
    pieces, sources, used = [], [], 0
    for hit in hits:
        record = hit.record
        body = escape_tags(record.text)
        if sources and used + len(body) > max_chars:
            break
        if not sources and len(body) > max_chars:
            body = body[:max_chars] + " ..."
        sid = f"S{len(sources) + 1}"
        attrs = {"id": sid, "title": _attr(record.title)}
        if record.heading_path:
            attrs["section"] = _attr(" / ".join(record.heading_path))
        pieces.append(xml_block("source", body, **attrs))
        sources.append(SourceRef(sid, record))
        used += len(body)
    text = xml_block("untrusted_data", "\n".join(pieces), label="retrieved_sources") if pieces else ""
    return SourceBundle(text, sources)
