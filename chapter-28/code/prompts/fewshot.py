"""Few-shot examples: render them, choose them, and check that they are correct."""
import re
from dataclasses import dataclass

from .structured import StructuredOutputError, extract_json, validate


@dataclass(frozen=True)
class Example:
    input: str
    output: str


def render_examples(examples: list) -> str:
    """Render examples as <examples><example><input>..</input><output>..</output></example></examples>."""
    if not examples:
        return ""
    parts = ["<examples>"]
    for ex in examples:
        parts.append(f"<example>\n<input>\n{ex.input}\n</input>\n<output>\n{ex.output}\n</output>\n</example>")
    parts.append("</examples>")
    return "\n".join(parts)


def _words(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def select_examples(pool: list, query: str, k: int = 3) -> list:
    """Pick the k examples whose input shares the most words with the query.

    Ties keep the pool's original order, so the result is predictable. A simple
    stand-in for the embedding search of Chapter 31.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    query_words = _words(query)

    def score(item):
        index, ex = item
        words = _words(ex.input)
        overlap = len(query_words & words) / (len(query_words | words) or 1)
        return (-overlap, index)

    return [ex for _, ex in sorted(enumerate(pool), key=score)[:k]]


def check_examples(examples: list, schema: dict) -> list:
    """Return problems found in the example OUTPUTS. A wrong example teaches the wrong thing."""
    problems = []
    for number, ex in enumerate(examples, start=1):
        try:
            data = extract_json(ex.output)
        except StructuredOutputError as error:
            problems.append(f"example {number}: {error}")
            continue
        problems.extend(f"example {number}: {p}" for p in validate(data, schema))
    return problems
