"""Embeddings: turning text into vectors, and comparing vectors.

Anthropic does not offer an embedding model, so you pair Claude with another
provider (Voyage AI is the one Anthropic's docs point to), with OpenAI, or with
an open-source model you run yourself. The comparison maths is the same for all.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

Vector = Sequence[float]


def dot(a: Vector, b: Vector) -> float:
    if len(a) != len(b):
        raise ValueError(
            f"Vectors must have the same length, got {len(a)} and {len(b)}. "
            "Did you mix two different embedding models?"
        )
    return sum(x * y for x, y in zip(a, b))


def norm(a: Vector) -> float:
    return math.sqrt(sum(x * x for x in a))


def cosine_similarity(a: Vector, b: Vector) -> float:
    """1.0 = same direction (very similar), 0 = unrelated, -1 = opposite."""
    na, nb = norm(a), norm(b)
    if na == 0 or nb == 0:
        raise ValueError("Cannot compare a zero vector.")
    return dot(a, b) / (na * nb)


@dataclass(frozen=True)
class Hit:
    index: int
    text: str
    score: float


def top_k(
    query: Vector, vectors: Sequence[Vector], texts: Sequence[str], k: int = 3
) -> list[Hit]:
    """Brute-force nearest neighbours. Fine for thousands of items.

    Chapter 31 moves this into PostgreSQL with pgvector, which does the same
    thing with an index so it stays fast at millions.
    """
    if len(vectors) != len(texts):
        raise ValueError("vectors and texts must be the same length")
    scored = [Hit(i, texts[i], cosine_similarity(query, v)) for i, v in enumerate(vectors)]
    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[:k]


class Embedder(Protocol):
    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAICompatEmbedder:
    """Works with OpenAI and with local servers such as Ollama that expose /v1/embeddings."""

    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(model=self.model, input=list(texts))
        ordered = sorted(response.data, key=lambda d: d.index)
        return [list(d.embedding) for d in ordered]
