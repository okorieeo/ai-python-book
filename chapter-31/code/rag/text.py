"""Shared text analysis: the same tokens feed the toy embedder and the keyword index."""
import re

STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from has have how i if in is it its my of on or "
    "our that the their there this to was we what when where which who why will with you your".split()
)
_TOKEN = re.compile(r"[a-z0-9_]+")


def stem(token: str) -> str:
    """A very small stemmer: 'plans' -> 'plan'. Real systems use a proper language analyzer."""
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def analyze(text: str) -> list:
    """Lowercase, split into words, drop stop words and stem. Identifiers like err_4021 survive."""
    return [stem(t) for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]
