"""Chunk records and an in-memory vector store with the same shape as the Postgres one."""
from dataclasses import dataclass, field
from typing import Optional

from .embeddings import cosine
from .lexical import BM25Index


@dataclass
class ChunkRecord:
    """One stored chunk. The Django model KnowledgeChunk holds the same fields."""

    doc_id: str
    owner_id: str
    index: int
    title: str
    text: str
    start: int
    end: int
    heading_path: tuple = ()
    context: str = ""                 # optional situating context (28 contextual retrieval, 31.6)
    embedding: Optional[list] = None
    embedding_model: str = ""
    injection_risk: str = "none"

    @property
    def key(self) -> str:
        return f"{self.doc_id}:{self.index}"

    @property
    def section(self) -> str:
        return " > ".join(self.heading_path)


class InMemoryStore:
    """Brute-force search over a Python list. Fine for tests and small data, not for production.

    EVERY search takes an owner_id and only sees that owner's chunks. This is the rule that
    keeps one customer's documents out of another customer's answers.
    """

    def __init__(self):
        self._records = {}       # key -> ChunkRecord
        self._hashes = {}        # doc_id -> content hash
        self._lexical = {}       # owner_id -> BM25Index (rebuilt when data changes)

    def document_hash(self, doc_id: str) -> Optional[str]:
        return self._hashes.get(doc_id)

    def replace_document(self, doc_id: str, doc_hash: str, records: list) -> None:
        self.delete_document(doc_id)
        for record in records:
            self._records[record.key] = record
        self._hashes[doc_id] = doc_hash
        self._lexical.clear()

    def delete_document(self, doc_id: str) -> int:
        keys = [k for k, r in self._records.items() if r.doc_id == doc_id]
        for key in keys:
            del self._records[key]
        self._hashes.pop(doc_id, None)
        self._lexical.clear()
        return len(keys)

    def count(self, owner_id: Optional[str] = None) -> int:
        return sum(1 for r in self._records.values() if owner_id is None or r.owner_id == owner_id)

    def vector_search(self, query_vector: list, k: int, owner_id: str, model: str) -> list:
        """Return [(ChunkRecord, cosine similarity)] best first. Never mixes embedding models."""
        scored = [
            (r, cosine(query_vector, r.embedding))
            for r in self._records.values()
            if r.owner_id == owner_id and r.embedding_model == model and r.embedding is not None
        ]
        scored.sort(key=lambda item: (-item[1], item[0].key))
        return scored[:k]

    def lexical_search(self, query: str, k: int, owner_id: str) -> list:
        """Return [(ChunkRecord, BM25 score)] best first, for this owner only."""
        index = self._lexical.get(owner_id)
        if index is None:
            index = BM25Index()
            for r in self._records.values():
                if r.owner_id == owner_id:
                    index.add(r.key, (r.context + "\n" + r.text) if r.context else r.text)
            self._lexical[owner_id] = index
        return [(self._records[key], score) for key, score in index.search(query, k)]
