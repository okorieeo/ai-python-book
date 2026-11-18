from celery import shared_task

from rag.embeddings import EmbeddingError
from rag.ingest import IngestError, extract_text, ingest_document

from .models import KnowledgeDocument
from .services import get_embedder
from .store import PgVectorStore


@shared_task(bind=True, autoretry_for=(EmbeddingError,), retry_backoff=True, retry_backoff_max=600,
             retry_jitter=True, max_retries=5, acks_late=True)
def ingest_document_task(self, document_id: int) -> str:
    """Turn an uploaded file into searchable chunks. Safe to run twice for the same document."""
    document = KnowledgeDocument.objects.get(pk=document_id)
    document.status, document.error = KnowledgeDocument.Status.PROCESSING, ""
    document.save(update_fields=["status", "error", "updated_at"])
    try:
        with document.file.open("rb") as handle:
            text = extract_text(handle.read(), document.content_type)
        report = ingest_document(
            doc_id=str(document.pk), owner_id=str(document.owner_id), title=document.title, text=text,
            embedder=get_embedder(), store=PgVectorStore(),
        )
    except IngestError as error:                      # the file itself is the problem: do not retry
        document.status, document.error = KnowledgeDocument.Status.FAILED, str(error)[:300]
        document.save(update_fields=["status", "error", "updated_at"])
        return "failed"
    except EmbeddingError:
        if self.request.retries >= self.max_retries:  # out of retries: tell the user, keep the error short
            document.status, document.error = KnowledgeDocument.Status.FAILED, "The embedding service was unavailable."
            document.save(update_fields=["status", "error", "updated_at"])
            return "failed"
        raise                                          # autoretry_for schedules the next attempt
    document.status = KnowledgeDocument.Status.READY
    document.save(update_fields=["status", "updated_at"])
    return report.status
