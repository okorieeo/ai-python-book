"""Glue between Django settings and the framework-independent rag package."""
from functools import lru_cache

from django.conf import settings
from prompts.llm import AnthropicLLM
from prompts.registry import PromptRegistry

from rag.embeddings import VoyageEmbedder
from rag.pipeline import answer_question
from rag.retrieval import Retriever
from rag.validate_vectors import check_dimensions

from .store import PgVectorStore
from prompt_runs.recorder import django_recorder


@lru_cache(maxsize=1)
def get_embedder() -> VoyageEmbedder:
    embedder = VoyageEmbedder(model=settings.EMBEDDING_MODEL, dimensions=settings.EMBEDDING_DIMENSIONS)
    problems = check_dimensions(embedder.dimensions, settings.EMBEDDING_DIMENSIONS)
    if problems:
        raise RuntimeError(problems[0])
    return embedder


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever(get_embedder(), PgVectorStore(), k=5, candidates=20, mode="hybrid")


@lru_cache(maxsize=1)
def get_registry() -> PromptRegistry:
    return PromptRegistry(settings.BASE_DIR / "rag" / "prompt_library")


def ask(user, question: str, history=None):
    """Answer a question from this user's documents only."""
    return answer_question(question, owner_id=str(user.pk), retriever=get_retriever(),
                           registry=get_registry(), llm=AnthropicLLM(), history=history,
                           recorder=django_recorder)
