"""Handling text the model reads but nobody on our team wrote. Pure Python, no Django.

Task titles, notes and event descriptions are written by users, and tomorrow they may be
imported from
e-mails or shared calendars. To the model they all look like instructions. We do two
cheap things:
mark that text as DATA, and make sure it cannot forge the marker. Marking is a seat
belt, not a wall:
the real protection is that no tool call can do harm without server-side checks (see
agent.py).
"""
import json
import re

from core.security.sanitize import clean_text

# "<untrusted", "</untrusted", "< / untrusted"
_MARKER = re.compile(r"<\s*/?\s*untrusted", re.IGNORECASE)


def wrap_untrusted(text: str, *, source: str, max_length: int = 500) -> str:
    """Return `text` cleaned, shortened and wrapped as <untrusted
    source="...">...</untrusted>."""
    room = 10 * max_length  # generous: cleaning can only shrink the text
    # control and bidi characters removed
    cleaned = clean_text(str(text)[:room], max_length=room)
    # no forged opening or closing tags
    cleaned = _MARKER.sub("[removed]", cleaned)
    if len(cleaned) > max_length:
        cleaned = cleaned[: max_length - 1].rstrip() + "…"
    safe_source = re.sub(r"[^a-z0-9_.-]", "", source.lower())
    return f'<untrusted source="{safe_source}">{cleaned}</untrusted>'


def to_model_json(data, *, free_text: dict[str, int]) -> str:
    """Serialize a tool result, wrapping the named free-text fields wherever they
    appear.

    `free_text` maps a field name ("title", "notes") to its maximum length. Everything
    else
    (ids, dates, numbers, our own words) passes through unchanged.
    """

    def walk(value, key=None, path=""):
        if isinstance(value, dict):
            return {k: walk(v, k, f"{path}.{k}" if path else k) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v, key, path) for v in value]
        if isinstance(value, str) and key in free_text:
            return wrap_untrusted(value, source=key, max_length=free_text[key])
        return value

    return json.dumps(walk(data), ensure_ascii=False, separators=(",", ":"))
