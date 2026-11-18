"""BM25: classic keyword ranking. It catches exact words and identifiers that embeddings blur."""
import math
from collections import Counter

from .text import analyze


class BM25Index:
    """A small in-memory BM25 index. Postgres full-text search plays this role in production."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self._tf = {}          # key -> Counter of terms
        self._len = {}         # key -> number of terms
        self._postings = {}    # term -> set of keys

    def add(self, key: str, text: str) -> None:
        terms = analyze(text)
        self._tf[key] = Counter(terms)
        self._len[key] = len(terms)
        for term in self._tf[key]:
            self._postings.setdefault(term, set()).add(key)

    def __len__(self) -> int:
        return len(self._tf)

    def search(self, query: str, k: int = 10) -> list:
        """Return [(key, score)] best first. Documents with no query word are never returned."""
        n = len(self._tf)
        if not n:
            return []
        avg_len = sum(self._len.values()) / n or 1.0
        scores = {}
        for term in set(analyze(query)):
            keys = self._postings.get(term)
            if not keys:
                continue
            idf = math.log(1 + (n - len(keys) + 0.5) / (len(keys) + 0.5))
            for key in keys:
                tf = self._tf[key][term]
                norm = tf + self.k1 * (1 - self.b + self.b * self._len[key] / avg_len)
                scores[key] = scores.get(key, 0.0) + idf * tf * (self.k1 + 1) / norm
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:k]
