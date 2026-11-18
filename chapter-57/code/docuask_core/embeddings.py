"""Embedding interface, a deterministic stand-in for tests, and the Voyage AI client used in production.

Anthropic does not offer an embedding model; its documentation points to Voyage AI. Whatever you choose,
the rest of the app only sees the Embedder interface, so the provider can be swapped (section 57.8).
"""
import hashlib
import math
import re
import time
from typing import Callable, List, Protocol, Sequence

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an and are as at be by can do does for from has have how i if in is it its of on or our "
                  "per should that the their this to was we what when where which who will with you your".split())


class Embedder(Protocol):
    dimensions: int
    model_name: str

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]: ...
    def embed_query(self, text: str) -> List[float]: ...


def _stem(w: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)]
    return w


def _normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


class HashingEmbedder:
    """A bag-of-words embedder: each stemmed word is hashed into one of `dimensions` slots.

    It is NOT semantic: "car" and "automobile" are unrelated to it. It exists so that tests and the evaluation
    harness run offline and give the same numbers every time. Never ship it as your production embedder."""

    model_name = "hashing-bow"

    def __init__(self, dimensions: int = 512):
        self.dimensions = dimensions

    def _embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dimensions
        for w in _WORD.findall(text.lower()):
            if w in _STOP:
                continue
            h = int.from_bytes(hashlib.blake2b(_stem(w).encode(), digest_size=8).digest(), "big")
            vec[h % self.dimensions] += 1.0 if (h >> 63) & 1 else -1.0
        return _normalize(vec)

    def embed_documents(self, texts):
        return [self._embed(t) for t in texts]

    def embed_query(self, text):
        return self._embed(text)


class TransientEmbeddingError(Exception):
    """A rate limit, a timeout or a 5xx from the provider: worth retrying."""


def with_retries(fn: Callable[[], object], attempts: int = 5, base_delay: float = 1.0, max_delay: float = 30.0,
                 sleep: Callable[[float], None] = time.sleep):
    for attempt in range(attempts):
        try:
            return fn()
        except TransientEmbeddingError:
            if attempt == attempts - 1:
                raise
            sleep(min(max_delay, base_delay * (2 ** attempt)))


def embed_in_batches(embedder: Embedder, texts: Sequence[str], batch_size: int = 64,
                     max_chars_per_batch: int = 200_000, sleep: Callable[[float], None] = time.sleep) -> List[List[float]]:
    """Embed many texts in provider-friendly batches (by count AND by total size), with retries."""
    out: List[List[float]] = []
    batch: List[str] = []
    size = 0

    def flush():
        nonlocal batch, size
        if batch:
            current = list(batch)
            out.extend(with_retries(lambda: embedder.embed_documents(current), sleep=sleep))
            batch, size = [], 0

    for t in texts:
        if batch and (len(batch) >= batch_size or size + len(t) > max_chars_per_batch):
            flush()
        batch.append(t)
        size += len(t)
    flush()
    if len(out) != len(texts):
        raise RuntimeError("embedding provider returned a different number of vectors than texts")
    return out


class VoyageEmbedder:
    """Production embedder using the `voyageai` package.   NOT executed in this book's test environment (no API key).

    pip install -U voyageai      (version 0.3.7 or later is needed for keys created in MongoDB Atlas)
    export VOYAGE_API_KEY=...
    Voyage vectors are normalised to length 1, so dot product equals cosine similarity.
    `input_type` matters: use "document" when indexing and "query" when searching."""

    def __init__(self, model: str = "voyage-4", dimensions: int = 1024):
        import voyageai
        self._client = voyageai.Client()
        self.model_name = model
        self.dimensions = dimensions

    def _embed(self, texts, input_type):
        try:
            kwargs = {} if self.dimensions == 1024 else {"output_dimension": self.dimensions}
            return self._client.embed(list(texts), model=self.model_name, input_type=input_type, **kwargs).embeddings
        except Exception as exc:   # narrow this to the SDK's rate-limit / timeout / server errors in your project
            if any(s in type(exc).__name__ for s in ("RateLimit", "Timeout", "ServiceUnavailable", "APIConnection")):
                raise TransientEmbeddingError(str(exc)) from exc
            raise

    def embed_documents(self, texts):
        return self._embed(texts, "document")

    def embed_query(self, text):
        return self._embed([text], "query")[0]
