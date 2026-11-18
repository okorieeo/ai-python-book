"""Consent as an append-only event log. The newest event for a purpose decides."""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


class Purpose(enum.StrEnum):
    TERMS = "terms"                  # acceptance of the Terms of Service (a contract, not a choice)
    PRIVACY_NOTICE = "privacy_notice"  # acknowledgement that the notice was shown
    ANALYTICS = "analytics"          # optional
    IMPROVEMENT = "improvement"      # optional: use my conversations to improve the product
    MARKETING = "marketing"          # optional


REQUIRED = frozenset({Purpose.TERMS, Purpose.PRIVACY_NOTICE})
OPTIONAL = frozenset(set(Purpose) - REQUIRED)


@dataclass(frozen=True)
class ConsentEvent:
    purpose: Purpose
    granted: bool
    document_version: str
    at: datetime


def current_state(events) -> dict[Purpose, ConsentEvent]:
    """Latest event per purpose. Ties on time go to the event that comes later in the list."""
    latest: dict[Purpose, ConsentEvent] = {}
    for _, event in sorted(enumerate(events), key=lambda pair: (pair[1].at, pair[0])):
        latest[event.purpose] = event
    return latest


def has_consent(events, purpose: Purpose, *, required_version: str | None = None) -> bool:
    """True only if the newest event grants it (and, if asked, for the current text)."""
    event = current_state(events).get(purpose)
    if event is None or not event.granted:
        return False
    return required_version is None or event.document_version == required_version


def missing_required(events, current_versions: dict[Purpose, str]) -> list[Purpose]:
    """Required documents the user must (re)accept: never accepted, or the text changed."""
    return [
        purpose
        for purpose in sorted(REQUIRED)
        if not has_consent(events, purpose, required_version=current_versions[purpose])
    ]
