"""The Postgres version of rag.store.InMemoryStore: same methods, same owner rule."""
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import transaction
from pgvector.django import CosineDistance

from rag.store import ChunkRecord

from .models import KnowledgeChunk, KnowledgeDocument


def _record(row: KnowledgeChunk) -> ChunkRecord:
    return ChunkRecord(
        doc_id=str(row.document_id), owner_id=str(row.owner_id), index=row.index, title=row.document.title,
        text=row.text, start=row.start, end=row.end, heading_path=tuple(row.heading_path), context=row.context,
        embedding=None, embedding_model=row.embedding_model, injection_risk=row.injection_risk,
    )


class PgVectorStore:
    """Chunks live in one table. Every query filters by owner and by embedding model."""

    def document_hash(self, doc_id: str):
        return KnowledgeDocument.objects.filter(pk=doc_id).values_list("content_hash", flat=True).first() or None

    @transaction.atomic
    def replace_document(self, doc_id: str, doc_hash: str, records: list) -> None:
        document = KnowledgeDocument.objects.select_for_update().get(pk=doc_id)
        document.chunks.all().delete()
        KnowledgeChunk.objects.bulk_create([
            KnowledgeChunk(
                document=document, owner_id=document.owner_id, index=r.index, text=r.text, context=r.context,
                start=r.start, end=r.end, heading_path=list(r.heading_path), injection_risk=r.injection_risk,
                embedding=r.embedding, embedding_model=r.embedding_model,
            ) for r in records
        ], batch_size=200)
        document.chunks.update(search_vector=SearchVector("context", "text", config="english"))
        document.content_hash, document.chunk_count = doc_hash, len(records)
        document.save(update_fields=["content_hash", "chunk_count", "updated_at"])

    def delete_document(self, doc_id: str) -> int:
        deleted, _ = KnowledgeChunk.objects.filter(document_id=doc_id).delete()
        return deleted

    def vector_search(self, query_vector: list, k: int, owner_id: str, model: str) -> list:
        rows = (KnowledgeChunk.objects
                .filter(owner_id=owner_id, embedding_model=model, document__status="ready")
                .select_related("document")
                .annotate(distance=CosineDistance("embedding", query_vector))
                .order_by("distance")[:k])
        return [(_record(row), 1.0 - row.distance) for row in rows]      # cosine distance -> similarity

    def lexical_search(self, query: str, k: int, owner_id: str) -> list:
        search = SearchQuery(query, search_type="websearch", config="english")
        rows = (KnowledgeChunk.objects
                .filter(owner_id=owner_id, document__status="ready", search_vector=search)
                .select_related("document")
                .annotate(rank=SearchRank("search_vector", search))
                .order_by("-rank")[:k])
        return [(_record(row), float(row.rank)) for row in rows]
