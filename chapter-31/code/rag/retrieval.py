"""Finding the right chunks: vector search, keyword search, fusion and filters."""
from dataclasses import dataclass
from typing import Optional

from .fusion import reciprocal_rank_fusion
from .store import ChunkRecord
from .text import analyze

_RISK_ORDER = {"none": 0, "low": 1, "high": 2}


@dataclass
class Hit:
    record: ChunkRecord
    score: float                       # the score used for ordering (fused or single-list)
    similarity: Optional[float] = None  # cosine similarity, when vector search found it
    vector_rank: Optional[int] = None   # 1-based rank in the vector list
    lexical_rank: Optional[int] = None  # 1-based rank in the keyword list


class KeywordReranker:
    """A TOY reranker: prefers chunks that contain more of the question's words.

    Real rerankers are cross-encoder models that read the question and the chunk together.
    Anything with the method rerank(query, hits) -> hits can replace this one.
    """

    def rerank(self, query: str, hits: list) -> list:
        terms = set(analyze(query))
        def overlap(hit):
            words = set(analyze(hit.record.text))
            return len(terms & words) / (len(terms) or 1)
        return sorted(hits, key=lambda h: (-overlap(h), -h.score))


class Retriever:
    """Hybrid retrieval for one embedding model and one store.

    mode: "vector", "keyword" or "hybrid" (both lists merged with reciprocal rank fusion).
    min_similarity: vector candidates below this cosine similarity are dropped, so a question
        the documents cannot answer returns nothing instead of the "least bad" chunks.
    max_injection_risk: chunks flagged above this level at ingestion are left out.
    """

    def __init__(self, embedder, store, *, k: int = 5, candidates: int = 20, mode: str = "hybrid",
                 min_similarity: float = 0.15, rrf_k: int = 60, max_per_doc: Optional[int] = None,
                 max_injection_risk: str = "low", reranker=None):
        if mode not in {"vector", "keyword", "hybrid"}:
            raise ValueError("mode must be vector, keyword or hybrid")
        if max_injection_risk not in _RISK_ORDER:
            raise ValueError("max_injection_risk must be none, low or high")
        self.embedder, self.store = embedder, store
        self.k, self.candidates, self.mode = k, candidates, mode
        self.min_similarity, self.rrf_k = min_similarity, rrf_k
        self.max_per_doc, self.max_injection_risk, self.reranker = max_per_doc, max_injection_risk, reranker

    def search(self, query: str, owner_id: str, *, k: Optional[int] = None, mode: Optional[str] = None) -> list:
        k, mode = k or self.k, mode or self.mode
        by_key, similarity, vrank, lrank = {}, {}, {}, {}
        if mode in {"vector", "hybrid"}:
            query_vector = self.embedder.embed_query(query)
            found = self.store.vector_search(query_vector, self.candidates, owner_id, self.embedder.model)
            for rank, (record, sim) in enumerate((f for f in found if f[1] >= self.min_similarity), start=1):
                by_key[record.key] = record
                similarity[record.key], vrank[record.key] = sim, rank
        if mode in {"keyword", "hybrid"}:
            for rank, (record, _score) in enumerate(self.store.lexical_search(query, self.candidates, owner_id), start=1):
                by_key[record.key] = record
                lrank[record.key] = rank
        if mode == "vector":
            ordered = sorted(vrank, key=vrank.get)
            scores = {key: similarity[key] for key in ordered}
        elif mode == "keyword":
            ordered = sorted(lrank, key=lrank.get)
            scores = {key: 1.0 / (self.rrf_k + lrank[key]) for key in ordered}
        else:
            fused = reciprocal_rank_fusion([sorted(vrank, key=vrank.get), sorted(lrank, key=lrank.get)], self.rrf_k)
            ordered, scores = [key for key, _ in fused], dict(fused)

        limit = _RISK_ORDER[self.max_injection_risk]
        hits = [
            Hit(by_key[key], scores[key], similarity.get(key), vrank.get(key), lrank.get(key))
            for key in ordered if _RISK_ORDER.get(by_key[key].injection_risk, 2) <= limit
        ]
        if self.reranker:
            hits = self.reranker.rerank(query, hits)
        if self.max_per_doc:
            kept, per_doc = [], {}
            for hit in hits:
                per_doc[hit.record.doc_id] = per_doc.get(hit.record.doc_id, 0) + 1
                if per_doc[hit.record.doc_id] <= self.max_per_doc:
                    kept.append(hit)
            hits = kept
        return hits[:k]
