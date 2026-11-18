"""Measuring retrieval: did the right document come back, and how high did it rank?"""
from dataclasses import dataclass, field


@dataclass
class RetrievalCase:
    question: str
    relevant_docs: frozenset        # doc ids that contain the answer
    owner_id: str = "acme"
    id: str = ""


@dataclass
class CaseOutcome:
    case: RetrievalCase
    rank: int                       # 1-based rank of the first relevant document, 0 if missing
    returned_docs: list = field(default_factory=list)


@dataclass
class RetrievalReport:
    label: str
    k: int
    outcomes: list

    @property
    def hit_rate(self) -> float:
        """Share of questions with a relevant document in the top k (also called recall@k for one answer)."""
        return sum(1 for o in self.outcomes if o.rank) / len(self.outcomes) if self.outcomes else 0.0

    @property
    def mrr(self) -> float:
        """Mean reciprocal rank: 1.0 if the answer is always first, 0.5 if always second, 0 if missing."""
        return sum(1 / o.rank for o in self.outcomes if o.rank) / len(self.outcomes) if self.outcomes else 0.0

    def misses(self) -> list:
        return [o.case.id or o.case.question for o in self.outcomes if not o.rank]


def evaluate_retrieval(retriever, cases: list, *, k: int = 3, mode: str = None, label: str = "") -> RetrievalReport:
    """Run every case through the retriever and record the rank of the first relevant document."""
    outcomes = []
    for case in cases:
        hits = retriever.search(case.question, case.owner_id, k=k, mode=mode)
        docs = []
        for hit in hits:                       # unique documents, in rank order
            if hit.record.doc_id not in docs:
                docs.append(hit.record.doc_id)
        rank = next((i for i, d in enumerate(docs, start=1) if d in case.relevant_docs), 0)
        outcomes.append(CaseOutcome(case, rank, docs))
    return RetrievalReport(label or (mode or retriever.mode), k, outcomes)


def format_comparison(reports: list) -> str:
    """One row per configuration: hit rate, MRR and the questions that missed."""
    lines = [f"{'setting':<10} {'hit@' + str(reports[0].k):>7} {'MRR':>6}  missed", "-" * 64]
    for r in reports:
        missed = ", ".join(r.misses()) or "-"
        lines.append(f"{r.label:<10} {r.hit_rate:>7.2f} {r.mrr:>6.2f}  {missed}")
    return "\n".join(lines)
