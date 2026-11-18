"""Check that an answer's citations point at real sources and that quotes really appear there."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_MARKER = re.compile(r"\[(\d+)\]")
_QUOTE_THEN_MARKER = re.compile(r"[\"“]([^\"”]{12,300})[\"”]\s*\[(\d+)\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
ABSTAIN_PHRASES = ("i could not find", "i couldn't find", "the sources do not", "not enough information")


@dataclass(frozen=True)
class Source:
    id: int
    title: str
    text: str


@dataclass(frozen=True)
class Issue:
    kind: str    # unknown_source | quote_not_found | uncited_number | no_citations
    detail: str


@dataclass
class Verification:
    ok: bool
    issues: list[Issue] = field(default_factory=list)
    cited: set[int] = field(default_factory=set)


def _norm(text: str) -> str:
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def abstained(answer: str) -> bool:
    lowered = answer.lower()
    return any(phrase in lowered for phrase in ABSTAIN_PHRASES)


def verify_citations(answer: str, sources: list[Source], *, require_citations: bool = True) -> Verification:
    by_id = {s.id: s for s in sources}
    issues: list[Issue] = []
    cited = {int(n) for n in _MARKER.findall(answer)}

    for n in sorted(cited):
        if n not in by_id:
            issues.append(Issue("unknown_source", f"[{n}] does not exist"))

    for quote, n in _QUOTE_THEN_MARKER.findall(answer):
        source = by_id.get(int(n))
        if source is not None and _norm(quote) not in _norm(source.text):
            issues.append(Issue("quote_not_found", f"quote attributed to [{n}] is not in that source"))

    if abstained(answer):
        return Verification(not issues, issues, cited)

    if require_citations and not cited:
        issues.append(Issue("no_citations", "the answer cites nothing"))
    elif require_citations:
        for sentence in _SENTENCE.split(answer):
            if re.search(r"\d", sentence) and not _MARKER.search(sentence):
                issues.append(Issue("uncited_number", sentence.strip()[:80]))
    return Verification(not issues, issues, cited)
