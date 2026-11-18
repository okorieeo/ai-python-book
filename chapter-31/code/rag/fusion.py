"""Combining ranked lists (reciprocal rank fusion) and removing near-duplicates (MMR)."""
from .embeddings import cosine


def reciprocal_rank_fusion(rankings: list, k: int = 60) -> list:
    """Merge several best-first lists of keys into one list of (key, score).

    An item at rank r (starting at 1) in a list earns 1 / (k + r) from that list. Items that
    appear in several lists add up. Only ranks matter, never the raw scores, so lists with
    different scales (cosine similarity and BM25) combine without any tuning. Ties keep the
    order in which items first appeared.
    """
    scores, first_seen = {}, {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(key, len(first_seen))
    return sorted(scores.items(), key=lambda item: (-item[1], first_seen[item[0]]))


def mmr(candidates: list, k: int, lambda_: float = 0.7) -> list:
    """Maximal marginal relevance: pick results that are relevant AND different from each other.

    candidates: [(key, vector, relevance)] best first. lambda_ 1.0 means pure relevance, lower
    values punish similarity to what was already chosen. Returns the chosen keys in order.
    """
    remaining = list(candidates)
    chosen = []
    while remaining and len(chosen) < k:
        def value(item):
            _key, vector, relevance = item
            redundancy = max((cosine(vector, c[1]) for c in chosen), default=0.0)
            return lambda_ * relevance - (1 - lambda_) * redundancy
        best = max(remaining, key=value)
        chosen.append(best)
        remaining.remove(best)
    return [c[0] for c in chosen]
