from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from pgvector.django import HnswIndex, VectorField


class KnowledgeDocument(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        PROCESSING = "processing"
        READY = "ready"
        FAILED = "failed"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_documents")
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="knowledge/%Y/%m/")
    content_type = models.CharField(max_length=100)
    content_hash = models.CharField(max_length=64, blank=True)      # changes when text, model or chunking change
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    error = models.CharField(max_length=300, blank=True)            # a short, safe message for the user
    chunk_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.status})"


class KnowledgeChunk(models.Model):
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name="chunks")
    # Copied from the document so that EVERY search can filter by owner without a join.
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    index = models.PositiveIntegerField()
    text = models.TextField()
    context = models.TextField(blank=True)               # optional situating sentence (contextual retrieval)
    start = models.PositiveIntegerField()                # character offsets in the cleaned document text
    end = models.PositiveIntegerField()
    heading_path = models.JSONField(default=list)
    injection_risk = models.CharField(max_length=8, default="none")
    embedding = VectorField(dimensions=settings.EMBEDDING_DIMENSIONS)
    embedding_model = models.CharField(max_length=80)    # never mix vectors from different models
    search_vector = SearchVectorField(null=True)         # for keyword search

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "index"], name="uniq_chunk_index_per_document")]
        indexes = [
            HnswIndex(name="chunk_embedding_hnsw", fields=["embedding"], m=16, ef_construction=64,
                      opclasses=["vector_cosine_ops"]),
            GinIndex(fields=["search_vector"], name="chunk_search_gin"),
            models.Index(fields=["owner", "embedding_model"], name="chunk_owner_model_idx"),
        ]

    def __str__(self):
        return f"{self.document_id}:{self.index}"
