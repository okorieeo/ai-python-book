"""Hybrid search: vector similarity + keyword search, fused with Reciprocal Rank Fusion, ALWAYS scoped to one owner.

NOT executed in the book's test environment (needs PostgreSQL with pgvector)."""
from typing import List, Optional, Sequence, Tuple

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db import connection, transaction
from django.db.models import F
from pgvector.django import CosineDistance

from docuask_core.prompting import RetrievedChunk
from docuask_core.retrieval import fit_to_budget, limit_per_group, rrf

from .models import Chunk


def hybrid_search(owner, query_text: str, query_vec: Sequence[float], document_ids: Optional[Sequence[int]] = None,
                  k_each: int = 40, final_k: int = 8, max_per_document: int = 4,
                  token_budget: int = 6000) -> Tuple[List[RetrievedChunk], float]:
    """Returns (chunks in relevance order, best cosine similarity). The similarity feeds the no-answer gate."""
    # The owner filter is the tenant boundary. It is applied INSIDE the query, never after it.
    base = Chunk.objects.filter(owner=owner)
    if document_ids:
        base = base.filter(document_id__in=document_ids)

    with transaction.atomic():
        with connection.cursor() as cur:
            # A filtered HNSW search can return fewer rows than asked, because the filter runs after the index scan.
            # pgvector 0.8+ iterative scans keep scanning until enough rows survive the filter.
            cur.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
            cur.execute("SET LOCAL hnsw.max_scan_tuples = 20000")
            cur.execute("SET LOCAL hnsw.ef_search = %d" % 100)     # SET does not accept bound parameters
        by_vector = list(base.annotate(distance=CosineDistance("embedding", query_vec))
                         .order_by("distance").values("id", "distance")[:k_each])

    query = SearchQuery(query_text, config="english", search_type="websearch")
    by_keyword = list(base.filter(search_vector=query).annotate(rank=SearchRank(F("search_vector"), query))
                      .order_by("-rank").values_list("id", flat=True)[:k_each])

    best_similarity = 1.0 - by_vector[0]["distance"] if by_vector else 0.0
    fused = [cid for cid, _ in rrf([[r["id"] for r in by_vector], by_keyword])]
    rows = {c.id: c for c in base.filter(id__in=fused).select_related("document")}
    ordered = [cid for cid in fused if cid in rows]
    ordered = limit_per_group(ordered, lambda cid: rows[cid].document_id, max_per_document)[:final_k]
    ordered = fit_to_budget(ordered, lambda cid: rows[cid].tokens, token_budget)
    chunks = [RetrievedChunk(c.id, c.document_id, c.document.title, c.page_start, c.page_end, c.text)
              for c in (rows[cid] for cid in ordered)]
    return chunks, best_similarity
