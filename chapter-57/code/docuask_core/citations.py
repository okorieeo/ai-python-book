"""Turn the model's response into an answer the UI can show: text with [1] [2] markers plus verified citations.

The API returns citations on text blocks (type "search_result_location") when the search results are sent with
citations enabled. Response shape, as documented:
  {"type": "text", "text": "...", "citations": [{"type": "search_result_location", "cited_text": "...",
     "source": "chunk:7", "title": "...", "search_result_index": 0, "start_block_index": 0, "end_block_index": 1}]}
We never trust a pointer blindly: each citation is checked against the chunk we actually sent.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .prompting import RetrievedChunk

NO_ANSWER_TEXT = "I couldn't find that in your documents."


@dataclass
class Citation:
    marker: int
    chunk_id: int
    document_id: int
    title: str
    page_start: Optional[int]
    page_end: Optional[int]
    quotes: List[str] = field(default_factory=list)


@dataclass
class ParsedAnswer:
    text: str
    citations: List[Citation]
    dropped: int = 0            # citations that did not match what we sent (should be 0)
    grounded: bool = False      # at least one verified citation supports the answer
    refused: bool = False       # the model said it could not find the answer


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def parse_response(blocks: List[dict], retrieved: List[RetrievedChunk]) -> ParsedAnswer:
    by_marker: Dict[int, Citation] = {}
    marker_of_chunk: Dict[int, int] = {}
    dropped = 0
    out = []
    for block in blocks:
        if block.get("type") != "text":
            continue
        text = block.get("text", "")
        markers: List[int] = []
        for c in block.get("citations") or []:
            if c.get("type") != "search_result_location":
                dropped += 1
                continue
            idx = c.get("search_result_index")
            if not isinstance(idx, int) or not (0 <= idx < len(retrieved)):
                dropped += 1
                continue
            chunk = retrieved[idx]
            quote = c.get("cited_text", "")
            if c.get("source") != chunk.source or not quote or _squash(quote) not in _squash(chunk.text):
                dropped += 1
                continue
            if chunk.chunk_id not in marker_of_chunk:
                marker_of_chunk[chunk.chunk_id] = len(marker_of_chunk) + 1
                by_marker[marker_of_chunk[chunk.chunk_id]] = Citation(
                    marker_of_chunk[chunk.chunk_id], chunk.chunk_id, chunk.document_id, chunk.display_title,
                    chunk.page_start, chunk.page_end)
            m = marker_of_chunk[chunk.chunk_id]
            if quote not in by_marker[m].quotes:
                by_marker[m].quotes.append(quote)
            if m not in markers:
                markers.append(m)
        if markers:
            stripped = text.rstrip()
            text = stripped + "".join(f" [{m}]" for m in markers) + text[len(stripped):]
        out.append(text)
    answer = "".join(out).strip()
    citations = [by_marker[m] for m in sorted(by_marker)]
    refused = "couldn't find" in answer.lower() and not citations
    return ParsedAnswer(answer, citations, dropped, grounded=bool(citations), refused=refused)


class StreamAssembler:
    """Rebuilds the response blocks from streaming events, so streamed and non-streamed answers go through the
    same parse_response(). Citations arrive as `citations_delta` inside `content_block_delta` events."""

    def __init__(self):
        self.blocks: Dict[int, dict] = {}
        self.input_tokens = 0
        self.output_tokens = 0

    def feed(self, event: dict) -> Optional[str]:
        """Returns the new text to show the user, if the event carried any."""
        kind = event.get("type")
        if kind == "message_start":
            self.input_tokens = (event.get("message", {}).get("usage") or {}).get("input_tokens", 0)
        elif kind == "content_block_start":
            block = dict(event["content_block"])
            if block.get("type") == "text":
                block.setdefault("text", "")
                block["citations"] = list(block.get("citations") or [])
            self.blocks[event["index"]] = block
        elif kind == "content_block_delta":
            block = self.blocks.get(event["index"])
            delta = event["delta"]
            if block is None or block.get("type") != "text":
                return None
            if delta.get("type") == "text_delta":
                block["text"] += delta["text"]
                return delta["text"]
            if delta.get("type") == "citations_delta":
                block["citations"].append(delta["citation"])
        elif kind == "message_delta":
            self.output_tokens = (event.get("usage") or {}).get("output_tokens", self.output_tokens)
        return None

    def content(self) -> List[dict]:
        return [self.blocks[i] for i in sorted(self.blocks)]
