"""
Remove obvious personal data before text is logged or stored for review.

This catches PATTERNS: emails, card numbers (checked with the Luhn formula so ordinary long numbers survive)
and phone numbers. It cannot catch names, addresses or anything said in prose. Scrubbing reduces risk; it does
not make a conversation anonymous. Treat scrubbed text as still sensitive.
"""
from __future__ import annotations

import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CARD_CANDIDATE = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
PHONE_INTL = re.compile(r"(?<![\w+])\+\d{1,3}[\s.-]?\d{2,4}[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?!\d)")
PHONE_NATIONAL = re.compile(r"(?<!\d)0\d{2,3}[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")


def luhn_ok(digits: str) -> bool:
    """True if the digit string passes the Luhn checksum that real card numbers satisfy."""
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _card_sub(match: re.Match) -> str:
    digits = re.sub(r"[ -]", "", match.group(0))
    return "[CARD]" if luhn_ok(digits) else match.group(0)


def scrub_pii(text: str) -> str:
    text = EMAIL.sub("[EMAIL]", text)
    text = CARD_CANDIDATE.sub(_card_sub, text)
    text = PHONE_INTL.sub("[PHONE]", text)
    text = PHONE_NATIONAL.sub("[PHONE]", text)
    return text
