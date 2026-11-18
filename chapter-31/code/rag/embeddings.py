"""Embedding models: a common interface, a toy stand-in for tests and a Voyage AI adapter."""
import hashlib
import math
import os
from typing import Optional

from .text import analyze


class EmbeddingError(RuntimeError):
    """The embedding service failed or returned something unusable. Safe to retry later."""


def l2_normalize(vector: list) -> list:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else list(vector)


def cosine(a: list, b: list) -> float:
    """Cosine similarity: 1.0 means the same direction, 0 unrelated, -1 opposite."""
    if len(a) != len(b):
        raise ValueError(f"vector sizes differ: {len(a)} and {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def batched(items: list, size: int):
    """Yield lists of at most `size` items. Embedding APIs limit the size of one request."""
    for i in range(0, len(items), size):
        yield items[i:i + size]


# A tiny hand-written synonym table so the toy embedder can "understand" a few paraphrases.
TOY_SYNONYMS = {
    "reimburse": "refund", "reimbursement": "refund", "unsubscribe": "cancel", "terminate": "cancel",
    "erase": "delete", "remove": "delete", "download": "export", "cost": "price", "pricing": "price",
    "fee": "price", "maximum": "limit", "cap": "limit", "charged": "charge", "billed": "charge",
}


class HashingEmbedder:
    """A TOY embedder for tests and demos. It is NOT a real embedding model.

    It hashes words into a fixed number of buckets (with a small synonym table) and normalizes
    the result. Texts that share words get similar vectors, which is enough to exercise the
    pipeline for free, but it has no real understanding of meaning.
    """

    def __init__(self, dimensions: int = 256, synonyms: Optional[dict] = None):
        self.dimensions = dimensions
        self.model = f"toy-hashing-{dimensions}"
        self._synonyms = TOY_SYNONYMS if synonyms is None else synonyms

    def _embed(self, text: str) -> list:
        vector = [0.0] * self.dimensions
        for token in analyze(text):
            token = self._synonyms.get(token, token)
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            number = int.from_bytes(digest, "big")
            vector[number % self.dimensions] += 1.0 if (number >> 63) & 1 else -1.0
        return l2_normalize(vector)

    def embed_documents(self, texts: list) -> list:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list:
        return self._embed(text)


class VoyageEmbedder:
    """Embeddings from Voyage AI, the provider Anthropic recommends (pip install voyageai).

    The key comes from VOYAGE_API_KEY and the model from EMBEDDING_MODEL. Use input_type
    "document" for text you store and "query" for the user's question: the model treats
    them differently. Not executed in this chapter (no network access when it was written).
    """

    def __init__(self, model: Optional[str] = None, dimensions: Optional[int] = None, batch_size: int = 64):
        import voyageai  # imported here so the rest of the package needs no SDK

        self._client = voyageai.Client()
        self.model = model or os.environ.get("EMBEDDING_MODEL", "voyage-4")
        self.dimensions = dimensions or int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))
        self._batch_size = batch_size

    def _call(self, texts: list, input_type: str) -> list:
        try:
            result = self._client.embed(texts, model=self.model, input_type=input_type)
        except Exception as error:  # network, rate limit, bad key: let the caller retry
            raise EmbeddingError(f"Voyage request failed: {error}") from error
        vectors = result.embeddings
        if len(vectors) != len(texts) or any(len(v) != self.dimensions for v in vectors):
            raise EmbeddingError(
                f"Expected {len(texts)} vectors of {self.dimensions} numbers; got a different shape. "
                "Check EMBEDDING_DIMENSIONS against the model's documentation."
            )
        return vectors

    def embed_documents(self, texts: list) -> list:
        vectors = []
        for batch in batched(texts, self._batch_size):
            vectors.extend(self._call(batch, "document"))
        return vectors

    def embed_query(self, text: str) -> list:
        return self._call([text], "query")[0]
