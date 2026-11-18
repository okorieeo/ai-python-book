"""Command line for the AI Lab.  Run:  python -m ai_lab.lab --help"""
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import config
from .catalog import AS_OF, CATALOG, get_model, local_model, register
from .cost import conversation_usage, cost_usd
from .embeddings import OpenAICompatEmbedder, top_k, cosine_similarity
from .providers import (
    AnthropicProvider,
    ChatRequest,
    LLMProvider,
    Message,
    OpenAICompatProvider,
)
from .tokens import estimate_tokens

DEMO_DOCS = [
    "How do I reset my password?",
    "Steps to change your account password",
    "Our refund policy lasts 30 days",
    "The farm's egg production dropped last week",
    "Chickens laid fewer eggs this week",
]


def build_provider(kind: str) -> LLMProvider:
    if kind == "anthropic":
        config.require("ANTHROPIC_API_KEY")  # fail early with a friendly message
        return AnthropicProvider()
    if kind == "openai":
        return OpenAICompatProvider(
            name="openai", api_key=config.require("OPENAI_API_KEY"),
            base_url=config.optional("OPENAI_BASE_URL") or None,
        )
    if kind == "local":
        return OpenAICompatProvider(
            name="local",
            base_url=config.optional("LLM_BASE_URL", "http://localhost:11434/v1"),
            token_param="max_tokens",
        )
    raise SystemExit(f"Unknown provider {kind!r}. Use anthropic, openai or local.")


def _model_info(model_id: str):
    try:
        return get_model(model_id)
    except KeyError:
        return register(local_model(model_id)) if model_id not in CATALOG else get_model(model_id)


def cmd_models(args: argparse.Namespace) -> int:
    print(f"Model catalog (USD per million tokens, checked {AS_OF})")
    print(f"{'model id':<20}{'tier':<10}{'context':>10}{'in':>8}{'out':>8}{'cache read':>12}")
    for m in CATALOG.values():
        print(f"{m.model_id:<20}{m.tier:<10}{m.context_window:>10,}{m.price.input:>8.2f}"
              f"{m.price.output:>8.2f}{m.price.cache_read:>12.3f}")
    return 0


def cmd_count(args: argparse.Namespace) -> int:
    text = open(args.file, encoding="utf-8").read() if args.file else args.text
    print(f"characters: {len(text):,}")
    print(f"estimated tokens (rule of thumb): {estimate_tokens(text):,}")
    if args.exact:
        from .tokens import count_tokens_anthropic
        import anthropic

        config.require("ANTHROPIC_API_KEY")
        client = anthropic.Anthropic()
        exact = count_tokens_anthropic(
            client, model=args.model, messages=[{"role": "user", "content": text}]
        )
        print(f"exact input tokens for {args.model}: {exact:,}")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    provider = build_provider(args.provider)
    request = ChatRequest(
        model=args.model,
        messages=(Message("user", args.prompt),),
        system=args.system,
        max_tokens=args.max_tokens,
        effort=args.effort,
    )
    if args.stream:
        completion = None
        for chunk in provider.stream(request):
            if chunk.text:
                print(chunk.text, end="", flush=True)
            if chunk.completion:
                completion = chunk.completion
        print()
    else:
        completion = provider.complete(request)
        print(completion.text)
    assert completion is not None
    info = _model_info(args.model)
    cost = cost_usd(info, completion.usage)
    u = completion.usage
    print(f"\n--- {completion.model} via {completion.provider} | stop_reason={completion.stop_reason} "
          f"| {completion.latency_ms} ms")
    print(f"--- tokens: in={u.input_tokens:,} out={u.output_tokens:,} cache_read={u.cache_read_tokens:,} "
          f"| cost ${cost:.6f}")
    if completion.was_cut_off:
        print("--- WARNING: the reply hit max_tokens. Raise --max-tokens.")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    rows = []
    for spec in args.models:
        provider_kind, _, model_id = spec.partition(":")
        provider = build_provider(provider_kind)
        request = ChatRequest(model=model_id, messages=(Message("user", args.prompt),),
                              max_tokens=args.max_tokens, effort=args.effort)
        c = provider.complete(request)
        rows.append((model_id, c, cost_usd(_model_info(model_id), c.usage)))
    print(f"{'model':<22}{'ms':>7}{'in':>7}{'out':>7}{'cost USD':>12}  stop")
    for model_id, c, cost in rows:
        print(f"{model_id:<22}{c.latency_ms:>7}{c.usage.prompt_tokens:>7}{c.usage.output_tokens:>7}"
              f"{cost:>12.6f}  {c.stop_reason}")
    print("\nFirst 200 characters of each answer:")
    for model_id, c, _ in rows:
        print(f"\n[{model_id}] {c.text[:200]!r}")
    return 0


def cmd_chatcost(args: argparse.Namespace) -> int:
    print(f"A {args.turns}-turn chat: {args.system} system tokens, {args.user} tokens per "
          f"question, {args.reply} per reply. Every turn resends the history.")
    per_turn = conversation_usage(args.turns, system_tokens=args.system,
                                  user_tokens=args.user, reply_tokens=args.reply)
    sent = sum(u.input_tokens for u in per_turn)
    print(f"input tokens sent in total: {sent:,} (vs {args.turns * args.user:,} typed)")
    print(f"{'model':<20}{'total USD':>12}{'USD / 1000 chats':>20}")
    for m in CATALOG.values():
        c = sum(cost_usd(m, u) for u in per_turn)  # price each request, then add up
        print(f"{m.model_id:<20}{c:>12.4f}{c * 1000:>20.2f}")
    return 0


def cmd_similar(args: argparse.Namespace) -> int:
    import openai

    client = openai.OpenAI(
        api_key=config.optional("OPENAI_API_KEY", "not-needed-locally"),
        base_url=config.optional("EMBED_BASE_URL", "http://localhost:11434/v1"),
    )
    embedder = OpenAICompatEmbedder(client, args.embed_model)
    vectors = embedder.embed(DEMO_DOCS)
    query_vec = embedder.embed([args.query])[0]
    print(f"embedding model: {args.embed_model} | dimensions: {len(query_vec)}")
    for hit in top_k(query_vec, vectors, DEMO_DOCS, k=len(DEMO_DOCS)):
        print(f"  {hit.score:6.3f}  {hit.text}")
    return 0


def cmd_demo_vectors(args: argparse.Namespace) -> int:
    """Offline: three hand-made 3-number 'embeddings' so you can see cosine similarity."""
    cat, kitten, invoice = [0.9, 0.8, 0.1], [0.85, 0.75, 0.15], [0.1, 0.2, 0.95]
    print(f"cat vs kitten : {cosine_similarity(cat, kitten):.3f}")
    print(f"cat vs invoice: {cosine_similarity(cat, invoice):.3f}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ai_lab.lab", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("models", help="list models and prices (offline)").set_defaults(fn=cmd_models)

    c = sub.add_parser("count", help="estimate (and optionally count exactly) tokens")
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("--text")
    g.add_argument("--file")
    c.add_argument("--exact", action="store_true", help="ask Anthropic for the exact count")
    c.add_argument("--model", default=config.default_model())
    c.set_defaults(fn=cmd_count)

    a = sub.add_parser("ask", help="send one prompt to one model")
    a.add_argument("prompt")
    a.add_argument("--provider", choices=["anthropic", "openai", "local"], default="anthropic")
    a.add_argument("--model", default=config.default_model())
    a.add_argument("--system")
    a.add_argument("--max-tokens", type=int, default=1024)
    a.add_argument("--effort", choices=["low", "medium", "high"])
    a.add_argument("--stream", action="store_true")
    a.set_defaults(fn=cmd_ask)

    k = sub.add_parser("compare", help="same prompt, several models: provider:model ...")
    k.add_argument("prompt")
    k.add_argument("--models", nargs="+", required=True)
    k.add_argument("--max-tokens", type=int, default=1024)
    k.add_argument("--effort", choices=["low", "medium", "high"])
    k.set_defaults(fn=cmd_compare)

    cc = sub.add_parser("chatcost", help="what a long chat costs per model (offline)")
    cc.add_argument("--turns", type=int, default=10)
    cc.add_argument("--system", type=int, default=800)
    cc.add_argument("--user", type=int, default=150)
    cc.add_argument("--reply", type=int, default=400)
    cc.set_defaults(fn=cmd_chatcost)

    s = sub.add_parser("similar", help="rank sample sentences by embedding similarity")
    s.add_argument("query")
    s.add_argument("--embed-model", required=True)
    s.set_defaults(fn=cmd_similar)

    sub.add_parser("demo-vectors", help="cosine similarity with tiny vectors (offline)").set_defaults(
        fn=cmd_demo_vectors
    )

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except config.MissingSetting as exc:
        print(f"Configuration problem: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
