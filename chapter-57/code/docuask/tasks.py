"""Celery ingestion task: uploaded file -> pages -> chunks -> embeddings -> searchable rows.
NOT executed in the book's test environment."""
import logging

from celery import shared_task
from django.conf import settings
from django.contrib.postgres.search import SearchVector
from django.db import transaction

from docuask_core.chunking import chunk_pages
from docuask_core.embeddings import TransientEmbeddingError, VoyageEmbedder, embed_in_batches
from docuask_core.extract import ExtractionError, extract_pages
from docuask_core.limits import LimitExceeded, PLANS, billable_pages

from . import usage
from .models import Chunk, Document

log = logging.getLogger(__name__)


def get_embedder():
    return VoyageEmbedder(model=settings.EMBEDDING_MODEL, dimensions=settings.EMBEDDING_DIMENSIONS)


def _fail(doc: Document, message: str) -> None:
    if doc.pages_charged:
        usage.refund(doc.owner, "pages", doc.pages_charged)
    Document.objects.filter(pk=doc.pk).update(status=Document.Status.FAILED, error_message=message[:300], pages_charged=0)


@shared_task(bind=True, acks_late=True, autoretry_for=(TransientEmbeddingError,), retry_backoff=True,
             retry_backoff_max=300, retry_jitter=True, max_retries=5, soft_time_limit=900, time_limit=960)
def ingest_document(self, document_id: int) -> None:
    """Safe to run twice for the same document: it claims the row, rebuilds all chunks, and flips the status last."""
    with transaction.atomic():
        doc = Document.objects.select_for_update().select_related("owner").get(pk=document_id)
        if doc.status == Document.Status.READY:
            return                                             # a duplicate delivery: nothing to do
        doc.status = Document.Status.PROCESSING
        doc.error_message = ""
        doc.save(update_fields=["status", "error_message", "updated_at"])

    plan = PLANS[doc.owner.profile.plan]                      # however your billing app exposes the user's plan
    try:
        with doc.file.open("rb") as fh:
            pages = extract_pages(fh.read(), doc.original_filename, max_pages=plan.max_pages_per_file)
        needed = billable_pages(pages)
        if doc.pages_charged != needed:                       # a retry must not charge twice
            usage.consume(doc.owner, plan, "pages", needed - doc.pages_charged)
            Document.objects.filter(pk=doc.pk).update(pages_charged=needed)
            doc.pages_charged = needed
        chunks = chunk_pages(pages)
        if not chunks:
            raise ExtractionError("No readable text was found in this file.")
        embedder = get_embedder()
        vectors = embed_in_batches(embedder, [c.text for c in chunks], batch_size=64)   # may raise TransientEmbeddingError
    except ExtractionError as exc:
        _fail(doc, str(exc))                                  # the user's file is the problem: tell them, do not retry
        return
    except LimitExceeded as exc:
        _fail(doc, str(exc))
        return
    except TransientEmbeddingError:
        if self.request.retries >= self.max_retries:
            _fail(doc, "Our embedding service is busy. Please try again in a few minutes.")
        raise                                                 # autoretry_for schedules the retry with backoff
    except Exception:
        log.exception("ingestion failed for document %s", document_id)
        _fail(doc, "Something went wrong while processing this file. Please try again.")
        return

    with transaction.atomic():
        Chunk.objects.filter(document=doc).delete()           # idempotent: a retry starts from a clean slate
        Chunk.objects.bulk_create([
            Chunk(document=doc, owner_id=doc.owner_id, index=c.index, page_start=c.page_start, page_end=c.page_end,
                  text=c.text, tokens=c.tokens, sha256=c.sha256, embedding=v)
            for c, v in zip(chunks, vectors)], batch_size=200)
        Chunk.objects.filter(document=doc).update(search_vector=SearchVector("text", config="english"))
        Document.objects.filter(pk=doc.pk).update(
            status=Document.Status.READY, page_count=len(pages), chunk_count=len(chunks),
            embedding_model=embedder.model_name, error_message="")
