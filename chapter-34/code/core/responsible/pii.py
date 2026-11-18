"""Find personal data in text and swap it for placeholders before text leaves your servers.

Regular expressions catch the well-formed cases (emails, phone numbers, card numbers,
labelled ID numbers, IP addresses). They cannot find a name in free text, so we also accept
the terms we already know about, such as the signed-in user's own name.
This is one layer, not a guarantee: see section 34.5.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from ipaddress import IPv4Address

# Lower number = wins when two matches overlap.
_PRIORITY = {"CARD": 0, "ID": 1, "EMAIL": 2, "PHONE": 3, "IP": 4, "NAME": 5}

_EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_CARD = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
_PHONE = re.compile(r"(?<![\w.])[+(]?\d[\d ().-]{7,18}\d(?![\w:])")
_DATE_SHAPE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}[-/.]\d{2}[-/.]\d{4}")
_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
# "BVN: 22212345678", "my NIN is 12345678901", "SSN 123-45-6789", "passport number A1234567"
_LABELLED_ID = re.compile(
    r"(?i)\b(?:bvn|nin|ssn|tin|national\s+id|passport(?:\s+(?:no\.?|number))?)\b"
    r"[^\w\n]{0,6}(?:is\s+|=\s*)?(?P<value>[A-Z]{1,2}\d{6,8}|\d[\d-]{7,13}\d)"
)


@dataclass(frozen=True)
class Finding:
    kind: str
    start: int
    end: int
    text: str


def luhn_valid(number: str) -> bool:
    """The check-digit test that real card numbers pass and most random digits fail."""
    digits = [int(c) for c in number if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _looks_like_phone(candidate: str) -> bool:
    if _DATE_SHAPE.search(candidate):
        return False
    digits = re.sub(r"\D", "", candidate)
    if not 10 <= len(digits) <= 15:
        return False
    if candidate.startswith("+"):
        return True
    if candidate.startswith("0") and len(digits) in (10, 11):  # national format, e.g. 0803 123 4567
        return True
    has_separator = bool(re.search(r"[ ().-]", candidate))
    return has_separator and len(digits) in (10, 11)  # e.g. (415) 555-0132


def _valid_ipv4(text: str) -> bool:
    try:
        IPv4Address(text)
    except ValueError:
        return False
    return True


def find_pii(text: str, *, extra_terms: dict[str, str] | None = None) -> list[Finding]:
    """Return non-overlapping findings, in reading order.

    extra_terms maps a known string to a kind, e.g. {"Amina Bello": "NAME"}.
    """
    found: list[Finding] = []
    for m in _EMAIL.finditer(text):
        found.append(Finding("EMAIL", m.start(), m.end(), m.group()))
    for m in _CARD.finditer(text):
        if luhn_valid(m.group()):
            found.append(Finding("CARD", m.start(), m.end(), m.group()))
    for m in _LABELLED_ID.finditer(text):
        found.append(Finding("ID", m.start("value"), m.end("value"), m.group("value")))
    for m in _PHONE.finditer(text):
        if _looks_like_phone(m.group()):
            found.append(Finding("PHONE", m.start(), m.end(), m.group()))
    for m in _IPV4.finditer(text):
        if _valid_ipv4(m.group()):
            found.append(Finding("IP", m.start(), m.end(), m.group()))
    for term, kind in (extra_terms or {}).items():
        if len(term.strip()) < 3:
            continue  # a 1-2 letter "name" would match everywhere
        for m in re.finditer(re.escape(term), text, flags=re.IGNORECASE):
            found.append(Finding(kind, m.start(), m.end(), m.group()))

    accepted: list[Finding] = []
    for f in sorted(found, key=lambda f: (_PRIORITY.get(f.kind, 9), -(f.end - f.start), f.start)):
        if all(f.end <= a.start or f.start >= a.end for a in accepted):
            accepted.append(f)
    return sorted(accepted, key=lambda f: f.start)


class Pseudonymizer:
    """Replace personal data with stable placeholders, and put it back in the reply.

    One instance per request. The same value always gets the same placeholder, so the model
    can still reason ("email [EMAIL_1] twice"). The mapping lives in memory only: never log it.
    """

    def __init__(self, *, kinds: set[str] | None = None, extra_terms: dict[str, str] | None = None):
        self._kinds = kinds  # None = every kind
        self._extra_terms = extra_terms or {}
        self._by_value: dict[tuple[str, str], str] = {}
        self._originals: dict[str, str] = {}
        self._counts: dict[str, int] = {}

    def _placeholder(self, kind: str, value: str) -> str:
        key = (kind, value.lower() if kind in ("EMAIL", "NAME") else re.sub(r"\D", "", value) or value)
        if key not in self._by_value:
            self._counts[kind] = self._counts.get(kind, 0) + 1
            placeholder = f"[{kind}_{self._counts[kind]}]"
            self._by_value[key] = placeholder
            self._originals[placeholder] = value
        return self._by_value[key]

    def apply(self, text: str) -> str:
        pieces, last = [], 0
        for f in find_pii(text, extra_terms=self._extra_terms):
            if self._kinds is not None and f.kind not in self._kinds:
                continue
            pieces.append(text[last:f.start])
            pieces.append(self._placeholder(f.kind, f.text))
            last = f.end
        pieces.append(text[last:])
        return "".join(pieces)

    def restore(self, text: str) -> str:
        """Swap placeholders in the model's reply back to what the user typed."""
        for placeholder, original in self._originals.items():
            text = text.replace(placeholder, original)
        return text

    @property
    def redaction_count(self) -> int:
        """How many distinct values were replaced. Safe to log: it is only a number."""
        return len(self._originals)
