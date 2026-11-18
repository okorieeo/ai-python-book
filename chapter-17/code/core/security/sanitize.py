"""Small, dependency-free helpers for cleaning untrusted input."""
import re
import unicodedata

# Characters that can reorder text on screen (used to disguise names and titles).
_BIDI_CONTROLS = set("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def clean_text(value: str, *, max_length: int, single_line: bool = False) -> str:
    """Normalize user text without changing its meaning. Raises ValueError if too long.

    Removes control characters (NUL, escape codes...) and bidi overrides, normalizes
    Unicode so that "e" + combining accent equals "é", and trims the ends. Newlines
    and tabs are kept unless single_line is set.
    """
    value = unicodedata.normalize("NFC", value)
    kept = []
    for char in value:
        if char in _BIDI_CONTROLS:
            continue
        if unicodedata.category(char) == "Cc" and char not in "\t\n\r":
            continue
        kept.append(char)
    value = "".join(kept)
    if single_line:
        value = " ".join(value.split())
    value = value.strip()
    if len(value) > max_length:
        raise ValueError(f"Text may not be longer than {max_length} characters.")
    return value


def safe_filename(name: str, *, default: str = "file", max_length: int = 100) -> str:
    """Turn an uploaded file name into one that is safe to show, log and store."""
    name = unicodedata.normalize("NFKC", name).replace("\\", "/")
    name = name.split("/")[-1]  # drop any directory part
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if len(name) > max_length:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 10:
            name = stem[: max_length - len(ext) - 1] + "." + ext
        else:
            name = name[:max_length]
    return name or default


def build_filters(params, allowed: dict[str, str]) -> dict[str, str]:
    """Turn query-string parameters into ORM lookups, but ONLY the allowed ones.

    `allowed` maps a public parameter name to the ORM lookup it controls, for example
    {"q": "title__icontains", "after": "created_at__gte"}. Anything else in the query
    string is ignored, so a caller cannot reach into related models with names like
    user__password__startswith. Values are still strings: validate and convert them
    (a serializer or form) before using them.
    """
    return {
        lookup: params[name]
        for name, lookup in allowed.items()
        if params.get(name) not in (None, "")
    }
