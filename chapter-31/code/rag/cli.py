"""Command line helpers: python -m rag.cli <chunk|search|eval|ask|lock|check|live> ..."""
import argparse
import os
import sys
from pathlib import Path

from prompts.llm import ScriptedLLM
from prompts.registry import PromptRegistry

from .chunking import chunk_stats, fixed_size_chunks, markdown_chunks, paragraph_chunks
from .demo import CASES, build_demo, demo_answer_model
from .evaluate import evaluate_retrieval, format_comparison
from .pipeline import answer_question

LIBRARY = Path(__file__).resolve().parent / "prompt_library"
STRATEGIES = {"fixed": fixed_size_chunks, "paragraph": paragraph_chunks, "markdown": markdown_chunks}


def _show_hits(hits):
    for rank, hit in enumerate(hits, start=1):
        r = hit.record
        sim = f"{hit.similarity:.2f}" if hit.similarity is not None else "  - "
        print(f"{rank}. {r.doc_id:<9} sim={sim} vec#{hit.vector_rank or '-'} kw#{hit.lexical_rank or '-'}  {r.section or r.title}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="rag.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    chunk = sub.add_parser("chunk", help="chunk a text or Markdown file and print a summary")
    chunk.add_argument("path")
    chunk.add_argument("--strategy", choices=sorted(STRATEGIES), default="markdown")
    chunk.add_argument("--size", type=int, default=1000)
    search = sub.add_parser("search", help="search the demo knowledge base (toy embedder)")
    search.add_argument("query")
    search.add_argument("--mode", choices=["vector", "keyword", "hybrid"], default="hybrid")
    search.add_argument("--owner", default="acme")
    sub.add_parser("eval", help="compare vector, keyword and hybrid retrieval on the demo questions")
    ask = sub.add_parser("ask", help="ask the demo knowledge base a question (scripted stand-in model)")
    ask.add_argument("question")
    sub.add_parser("lock", help="add new prompt versions to rag/prompt_library/LOCK.json")
    sub.add_parser("check", help="verify the lock file")
    sub.add_parser("live", help="run the demo with Voyage embeddings and Claude (needs API keys)")
    args = parser.parse_args(argv)
    registry = PromptRegistry(LIBRARY)

    if args.command == "chunk":
        text = Path(args.path).read_text(encoding="utf-8")
        chunks = STRATEGIES[args.strategy](text, args.size) if args.strategy != "fixed" else fixed_size_chunks(text, args.size, args.size // 8)
        print(chunk_stats(chunks))
        for c in chunks[:5]:
            print(f"#{c.index} {c.tokens:>4} tokens  {' > '.join(c.heading_path) or '-'}  | {c.text[:60]!r}")
    elif args.command == "search":
        retriever, _ = build_demo()
        _show_hits(retriever.search(args.query, args.owner, mode=args.mode))
    elif args.command == "eval":
        retriever, _ = build_demo()
        print(format_comparison([evaluate_retrieval(retriever, CASES, k=3, mode=m) for m in ("vector", "keyword", "hybrid")]))
    elif args.command == "ask":
        retriever, _ = build_demo()
        result = answer_question(args.question, owner_id="acme", retriever=retriever, registry=registry,
                                 llm=ScriptedLLM(demo_answer_model))
        print(f"found: {result.found}  reason: {result.refused_reason or '-'}\nanswer: {result.answer}")
        for c in result.citations:
            print(f"  [{c.source_id}] {c.section or c.title}: \"{c.quote}\"")
        for p in result.problems:
            print(f"  problem: {p}")
    elif args.command == "lock":
        registry.write_lock()
        print("LOCK.json updated")
    elif args.command == "check":
        problems = registry.verify_lock()
        print("\n".join(problems) if problems else "LOCK.json OK")
        return 1 if problems else 0
    elif args.command == "live":
        from prompts.llm import AnthropicLLM
        from .embeddings import VoyageEmbedder
        if not os.environ.get("VOYAGE_API_KEY") or not os.environ.get("ANTHROPIC_API_KEY"):
            print("Set VOYAGE_API_KEY and ANTHROPIC_API_KEY first.")
            return 1
        embedder = VoyageEmbedder()
        retriever, _ = build_demo(embedder)
        print(f"embedding model: {embedder.model} ({embedder.dimensions} dimensions)")
        print(format_comparison([evaluate_retrieval(retriever, CASES, k=3, mode=m) for m in ("vector", "keyword", "hybrid")]))
        result = answer_question("How long do refunds take to arrive?", owner_id="acme", retriever=retriever,
                                 registry=registry, llm=AnthropicLLM())
        print(f"\nfound: {result.found}\nanswer: {result.answer}")
        for c in result.citations:
            print(f"  [{c.source_id}] {c.title}: \"{c.quote}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
