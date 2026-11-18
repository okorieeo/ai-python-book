"""The whole question-answering path: rewrite, retrieve, build sources, ask, verify."""
from dataclasses import dataclass, field
from typing import Optional

from prompts.blocks import clean_prompt_text
from prompts.runner import run_prompt
from prompts.structured import StructuredOutputError

from .answering import ANSWER_SCHEMA, NOT_FOUND_ANSWER, link_citations, verify_citations
from .context import build_sources
from .contextual import rewrite_query


@dataclass
class RagAnswer:
    answer: str
    found: bool
    citations: list = field(default_factory=list)      # [CitationLink], verified only
    problems: list = field(default_factory=list)       # what verification or checks complained about
    hits: list = field(default_factory=list)
    refused_reason: str = ""                            # why we did not give a grounded answer
    search_query: str = ""
    record: Optional[dict] = None                       # prompt id, tokens, latency (no text)


def _refuse(reason: str, query: str, hits=None, problems=None, record=None) -> RagAnswer:
    return RagAnswer(NOT_FOUND_ANSWER, False, [], problems or [], hits or [], reason, query, record)


def answer_question(question: str, *, owner_id: str, retriever, registry, llm, history: Optional[list] = None,
                    product_name: str = "AI Chat", recorder=None, max_source_chars: int = 12000) -> RagAnswer:
    """Answer from this owner's documents, or say that the answer is not there.

    The model is only called when retrieval found something. An answer is returned as grounded
    only if it has at least one citation whose quote was verified in the retrieved text.
    """
    question = clean_prompt_text(question, max_chars=2000)
    if not question:
        return _refuse("empty_question", "")

    query = rewrite_query(llm, registry, question, history or [])
    hits = retriever.search(query, owner_id)
    if not hits:
        return _refuse("no_relevant_sources", query)

    bundle = build_sources(hits, max_chars=max_source_chars)
    try:
        result = run_prompt(
            registry, llm, "answer_from_sources",
            {"product_name": product_name, "sources": bundle.text, "question": question},
            schema=ANSWER_SCHEMA, recorder=recorder, max_tokens=700,
        )
    except StructuredOutputError as error:
        return _refuse("model_output_invalid", query, hits, error.problems)

    data = result.data
    problems = verify_citations(data, bundle) + result.output_problems
    links = link_citations(data, bundle)
    if not data["found"]:
        return RagAnswer(data["answer"], False, [], problems, hits, "model_found_nothing", query, result.record)
    if not links:
        return _refuse("unverified_citations", query, hits, problems, result.record)
    return RagAnswer(data["answer"], True, links, problems, hits, "", query, result.record)
