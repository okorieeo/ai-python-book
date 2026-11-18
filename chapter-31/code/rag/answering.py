"""Grounded answers: the output schema and the checks that make citations trustworthy."""
import re
from dataclasses import dataclass
from typing import Optional

NOT_FOUND_ANSWER = "I could not find this in your documents."

ANSWER_SCHEMA = {
    "type": "object",
    "required": ["found", "answer", "citations"],
    "additionalProperties": False,
    "properties": {
        "found": {"type": "boolean"},
        "answer": {"type": "string", "minLength": 1, "maxLength": 1500},
        "citations": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "required": ["source_id", "quote"],
                "additionalProperties": False,
                "properties": {
                    "source_id": {"type": "string"},
                    "quote": {"type": "string", "minLength": 1, "maxLength": 400},
                },
            },
        },
    },
}

_MARKER = re.compile(r"\[(S\d+)\]")


def normalize_for_match(text: str) -> str:
    """Lowercase, unify quotes and dashes, and collapse whitespace, so harmless formatting
    differences do not make a correct quote look wrong."""
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2026", "...")
    return " ".join(text.lower().split())


def verify_citations(data: dict, bundle) -> list:
    """Return problems with the model's citations (empty list = all good).

    Checks: every cited source id was really given to the model, every quote appears word for
    word in that source, every [S#] marker in the answer matches a citation, and an answer that
    claims to be found has at least one citation.
    """
    problems = []
    cited_ids = set()
    for i, citation in enumerate(data.get("citations", []), start=1):
        source = bundle.get(citation["source_id"])
        if source is None:
            problems.append(f"citation {i}: unknown source {citation['source_id']}")
            continue
        cited_ids.add(citation["source_id"])
        if normalize_for_match(citation["quote"]) not in normalize_for_match(source.record.text):
            problems.append(f"citation {i}: the quote is not in {citation['source_id']}")
    for marker in _MARKER.findall(data.get("answer", "")):
        if bundle.get(marker) is None:
            problems.append(f"the answer mentions {marker}, which does not exist")
        elif marker not in cited_ids:
            problems.append(f"the answer mentions {marker} but has no verified citation for it")
    if data.get("found") and not data.get("citations"):
        problems.append("found is true but there are no citations")
    return problems


@dataclass
class CitationLink:
    source_id: str
    doc_id: str
    title: str
    section: str
    quote: str
    start: Optional[int]   # character offsets of the quote in the cleaned document text
    end: Optional[int]


def link_citations(data: dict, bundle) -> list:
    """Attach document, section and character offsets to each VALID citation, for the UI."""
    links = []
    for citation in data.get("citations", []):
        source = bundle.get(citation["source_id"])
        if source is None:
            continue
        record = source.record
        position = normalize_for_match(record.text).find(normalize_for_match(citation["quote"]))
        exact = record.text.lower().find(citation["quote"].lower())
        start = record.start + exact if exact >= 0 else None
        end = start + len(citation["quote"]) if start is not None else None
        if position < 0:
            continue
        links.append(CitationLink(source.id, record.doc_id, record.title, record.section,
                                  citation["quote"], start, end))
    return links
