"""Query rewriting and contextual retrieval: two small LLM steps around retrieval."""
from typing import Callable


def document_window(text: str, start: int, end: int, budget: int = 12000) -> str:
    """The part of the document around a chunk, small enough for a prompt.

    Short documents are returned whole. For long ones we keep the beginning (titles, intro) and
    the text around the chunk.
    """
    if len(text) <= budget:
        return text
    head = text[: budget // 4]
    room = budget - len(head)
    left = max(len(head), start - room // 2)
    right = min(len(text), left + room)
    return head + "\n[...]\n" + text[left:right]


def make_contextualizer(llm, registry, *, max_chars: int = 400) -> Callable:
    """Build the function that ingest_document calls for each chunk.

    It asks the model for a short sentence that situates the chunk in its document. The sentence
    is added to the chunk BEFORE embedding and keyword indexing, and is not shown to users.
    Costs one model call per chunk, so use a small model (and prompt caching, Chapter 33).
    """
    template = registry.get("contextualize_chunk")

    def contextualize(document_text: str, chunk) -> str:
        prompt = template.render({
            "document": document_window(document_text, chunk.start, chunk.end),
            "chunk": chunk.text,
        })
        reply = llm.complete(system=prompt.system, messages=prompt.messages, max_tokens=150)
        return " ".join(reply.text.split())[:max_chars]

    return contextualize


def format_history(messages: list, max_messages: int = 6, max_chars: int = 500) -> str:
    """Plain 'role: text' lines for the last few messages, each cut to a safe length."""
    lines = [f"{m['role']}: {' '.join(m['content'].split())[:max_chars]}" for m in messages[-max_messages:]]
    return "\n".join(lines)


def rewrite_query(llm, registry, question: str, history: list) -> str:
    """Make a follow-up question searchable on its own. Falls back to the original question."""
    if not history:
        return question
    prompt = registry.get("rewrite_query").render(
        {"history": format_history(history), "question": question})
    try:
        reply = llm.complete(system=prompt.system, messages=prompt.messages, max_tokens=100)
    except Exception:
        return question
    rewritten = " ".join(reply.text.split())
    return rewritten if 0 < len(rewritten) <= 300 else question
