import math
import re
import unicodedata

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_text(raw: str) -> str:
    """Clean text extracted from a PDF or Word file so that it chunks and embeds well.

    - removes NUL and other control characters (PostgreSQL text columns reject NUL)
    - folds ligatures and odd spaces (NFKC), so "ﬁnance" matches "finance"
    - re-joins words hyphenated across line breaks ("infor-\\nmation")
    - turns single line breaks inside a paragraph into spaces, keeps blank lines as paragraph breaks
    """
    text = unicodedata.normalize("NFKC", raw)
    text = _CTRL.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    paragraphs = re.split(r"\n\s*\n", text)
    cleaned = []
    for p in paragraphs:
        p = re.sub(r"\s*\n\s*", " ", p)
        p = re.sub(r"[ \t\u00a0]+", " ", p).strip()
        if p:
            cleaned.append(p)
    return "\n\n".join(cleaned)


def estimate_tokens(text: str) -> int:
    """A cheap estimate (about 4 characters per token for English). Real tokenizers differ by model and language,
    so use this for budgeting with a safety margin, never for billing."""
    return max(1, math.ceil(len(text) / 4)) if text else 0
