"""Measure retrieval quality BEFORE you trust the whole pipeline.

    python -m docuask_core.evals                     # offline, with the stand-in HashingEmbedder
    python -m docuask_core.evals --mode vector       # vector | keyword | hybrid

Answerable questions are scored with hit@k (is the right page in the top k?) and MRR (how high is it?).
Unanswerable questions measure the no-answer gate: the best similarity should stay below the threshold.
"""
import argparse
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .chunking import chunk_pages
from .embeddings import Embedder, HashingEmbedder, embed_in_batches
from .extract import extract_pages
from .retrieval import cosine, keyword_rank, rrf, vector_rank


@dataclass(frozen=True)
class IndexedChunk:
    id: int
    doc: str
    page: Optional[int]
    text: str
    vec: Tuple[float, ...]


def build_index(corpus_dir: str, embedder: Embedder, **chunk_kwargs) -> List[IndexedChunk]:
    pieces = []
    for name in sorted(os.listdir(corpus_dir)):
        with open(os.path.join(corpus_dir, name), "rb") as fh:
            pages = extract_pages(fh.read(), name)
        for c in chunk_pages(pages, **chunk_kwargs):
            pieces.append((name, c))
    vectors = embed_in_batches(embedder, [c.text for _, c in pieces])
    return [IndexedChunk(i, name, c.page_start, c.text, tuple(v)) for i, ((name, c), v) in enumerate(zip(pieces, vectors))]


def rank(index: List[IndexedChunk], embedder: Embedder, question: str, mode: str = "hybrid", k: int = 10) -> Tuple[List[int], float]:
    """Returns (ranked chunk ids, best vector similarity)."""
    qv = embedder.embed_query(question)
    by_vec = vector_rank(qv, [(c.id, c.vec) for c in index], k=50)
    best_sim = by_vec[0][1] if by_vec else 0.0
    if mode == "vector":
        return [i for i, _ in by_vec][:k], best_sim
    by_kw = keyword_rank(question, {c.id: c.text for c in index}, k=50)
    if mode == "keyword":
        return [i for i, _ in by_kw][:k], best_sim
    return [i for i, _ in rrf([[i for i, _ in by_vec], [i for i, _ in by_kw]])][:k], best_sim


@dataclass
class Report:
    mode: str
    answerable: int
    hit_at: Dict[int, float]
    mrr: float
    misses: List[str]
    sims_answerable: List[float]
    sims_unanswerable: List[float]


def evaluate(index, embedder, cases: Sequence[dict], mode: str = "hybrid", ks: Sequence[int] = (1, 3, 5)) -> Report:
    chunk = {c.id: c for c in index}
    hits = {k: 0 for k in ks}
    rr_sum, n, misses, sa, su = 0.0, 0, [], [], []
    for case in cases:
        ranked, sim = rank(index, embedder, case["question"], mode, max(ks))
        if not case["answerable"]:
            su.append(sim)
            continue
        n += 1
        sa.append(sim)
        position = next((i for i, cid in enumerate(ranked, 1)
                         if chunk[cid].doc == case["doc"] and chunk[cid].page == case["page"]), None)
        if position:
            rr_sum += 1.0 / position
            for k in ks:
                hits[k] += position <= k
        else:
            misses.append(case["question"])
    return Report(mode, n, {k: hits[k] / n for k in ks}, rr_sum / n, misses, sa, su)


def best_threshold(answerable: Sequence[float], unanswerable: Sequence[float]) -> Tuple[float, float]:
    """The similarity cut-off that classifies the most questions correctly (answer vs. refuse)."""
    candidates = sorted(set(answerable) | set(unanswerable))
    best = (0.0, 0.0)
    total = len(answerable) + len(unanswerable)
    for t in candidates:
        correct = sum(s >= t for s in answerable) + sum(s < t for s in unanswerable)
        if correct / total > best[1]:
            best = (t, correct / total)
    return best


def main(argv=None) -> int:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = argparse.ArgumentParser(prog="docuask_core.evals")
    p.add_argument("--corpus", default=os.path.join(here, "tests", "fixtures", "corpus"))
    p.add_argument("--cases", default=os.path.join(here, "tests", "fixtures", "eval_cases.json"))
    p.add_argument("--mode", choices=["vector", "keyword", "hybrid", "all"], default="all")
    p.add_argument("--embedder", choices=["hashing", "voyage"], default="hashing",
                   help="voyage needs the voyageai package and VOYAGE_API_KEY (not run in this book's test environment)")
    args = p.parse_args(argv)

    if args.embedder == "voyage":
        from .embeddings import VoyageEmbedder
        embedder = VoyageEmbedder()
    else:
        embedder = HashingEmbedder()
    index = build_index(args.corpus, embedder, target_tokens=60, max_tokens=100, min_tokens=15)
    with open(args.cases, encoding="utf-8") as fh:
        cases = json.load(fh)
    print(f"{len(index)} chunks from {len(set(c.doc for c in index))} documents, {len(cases)} questions (embedder: {embedder.model_name})\n")
    print(f"{'mode':<9}{'hit@1':>7}{'hit@3':>7}{'hit@5':>7}{'MRR':>8}")
    reports = []
    for mode in (["vector", "keyword", "hybrid"] if args.mode == "all" else [args.mode]):
        r = evaluate(index, embedder, cases, mode)
        reports.append(r)
        print(f"{mode:<9}{r.hit_at[1]:>7.2f}{r.hit_at[3]:>7.2f}{r.hit_at[5]:>7.2f}{r.mrr:>8.2f}")
    r = reports[-1]
    if r.misses:
        print(f"\nMissed by '{r.mode}':")
        for q in r.misses:
            print("  -", q)
    t, acc = best_threshold(r.sims_answerable, r.sims_unanswerable)
    print(f"\nNo-answer gate: best similarity for answerable questions {min(r.sims_answerable):.2f} to {max(r.sims_answerable):.2f}; "
          f"for unanswerable {min(r.sims_unanswerable):.2f} to {max(r.sims_unanswerable):.2f}")
    print(f"Best threshold on this set: {t:.2f} (classifies {acc:.0%} of questions correctly)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
