"""Ranking logic for retrieval. In production PostgreSQL does the vector and keyword searches (docuask/search.py);
the functions here fuse, filter and budget the results, and they also power the offline evaluation."""
import math
import re
from collections import Counter, defaultdict
from typing import Callable, Dict, Hashable, Iterable, List, Sequence, Tuple

_WORD = re.compile(r"[a-z0-9]+")


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def vector_rank(query_vec, items: Iterable[Tuple[Hashable, Sequence[float]]], k: int = 50) -> List[Tuple[Hashable, float]]:
    scored = [(key, cosine(query_vec, vec)) for key, vec in items]
    scored.sort(key=lambda kv: (-kv[1], str(kv[0])))
    return scored[:k]


def keyword_rank(query: str, docs: Dict[Hashable, str], k: int = 50) -> List[Tuple[Hashable, float]]:
    """A small BM25-style ranking. In production use PostgreSQL full-text search (SearchRank) instead."""
    tokenized = {key: _WORD.findall(text.lower()) for key, text in docs.items()}
    n = len(tokenized) or 1
    avg = sum(len(t) for t in tokenized.values()) / n or 1.0
    df = Counter(w for t in tokenized.values() for w in set(t))
    q = [w for w in _WORD.findall(query.lower())]
    scored = []
    for key, toks in tokenized.items():
        tf = Counter(toks)
        score = 0.0
        for w in q:
            if w in tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                score += idf * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * len(toks) / avg))
        if score > 0:
            scored.append((key, score))
    scored.sort(key=lambda kv: (-kv[1], str(kv[0])))
    return scored[:k]


def rrf(rank_lists: Sequence[Sequence[Hashable]], k: int = 60) -> List[Tuple[Hashable, float]]:
    """Reciprocal Rank Fusion: score(d) = sum over lists of 1 / (k + rank). It needs only ranks, so it can combine
    a cosine similarity and a keyword score even though those numbers are on completely different scales."""
    scores: Dict[Hashable, float] = defaultdict(float)
    for ranking in rank_lists:
        for rank, key in enumerate(ranking, start=1):
            scores[key] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], str(kv[0])))


def limit_per_group(ranked: Sequence[Hashable], group_of: Callable[[Hashable], Hashable], max_per_group: int) -> List[Hashable]:
    """Keep the order but allow at most `max_per_group` results from one document, so one long file cannot crowd out the rest."""
    seen: Counter = Counter()
    out = []
    for key in ranked:
        g = group_of(key)
        if seen[g] < max_per_group:
            seen[g] += 1
            out.append(key)
    return out


def drop_near_duplicates(ranked: Sequence[Hashable], vectors: Dict[Hashable, Sequence[float]], threshold: float = 0.97) -> List[Hashable]:
    kept: List[Hashable] = []
    for key in ranked:
        if all(cosine(vectors[key], vectors[other]) < threshold for other in kept):
            kept.append(key)
    return kept


def fit_to_budget(ranked: Sequence[Hashable], tokens_of: Callable[[Hashable], int], budget: int) -> List[Hashable]:
    """Take results in rank order until the token budget is used. Always keeps at least the first result."""
    out, used = [], 0
    for key in ranked:
        t = tokens_of(key)
        if out and used + t > budget:
            break
        out.append(key)
        used += t
    return out


def should_answer(best_similarity: float, threshold: float) -> bool:
    """The no-answer gate: if even the best passage is not similar enough, do not call the model at all."""
    return best_similarity >= threshold
