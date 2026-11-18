"""Data model for the Document Q&A platform.   (Django layer: written for this chapter, NOT executed in the book's
test environment, which had no Django or PostgreSQL. It is syntax-checked only. See the README.)"""
from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from pgvector.django import HnswIndex, VectorField

EMBEDDING_DIMENSIONS = 1024     # must match the embedding model's output size (voyage-4 default: 1024)


class Document(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "uploaded"
        PROCESSING = "processing"
        READY = "ready"
        FAILED = "failed"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    file = models.FileField(upload_to="uploads/%Y/%m/")        # private storage: never a public bucket (Chapter 16)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UPLOADED, db_index=True)
    error_message = models.CharField(max_length=300, blank=True)   # always safe to show to the user
    page_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    pages_charged = models.PositiveIntegerField(default=0)          # so a failed ingestion can be refunded
    embedding_model = models.CharField(max_length=64, blank=True)   # vectors from different models must never be mixed
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["owner", "sha256"], name="uniq_document_per_owner")]


class Chunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    # Denormalised on purpose: the search query filters on owner directly, without a join,
    # and a bug in a join can never leak another user's text.
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    index = models.PositiveIntegerField()
    page_start = models.PositiveIntegerField(null=True)
    page_end = models.PositiveIntegerField(null=True)
    text = models.TextField()
    tokens = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS)
    search_vector = SearchVectorField(null=True)

    class Meta:
        ordering = ["document_id", "index"]
        constraints = [models.UniqueConstraint(fields=["document", "index"], name="uniq_chunk_index")]
        indexes = [
            HnswIndex(name="chunk_embedding_hnsw", fields=["embedding"], m=16, ef_construction=64,
                      opclasses=["vector_cosine_ops"]),
            GinIndex(name="chunk_search_gin", fields=["search_vector"]),
            models.Index(fields=["owner", "document"], name="chunk_owner_doc"),
        ]


class Conversation(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=120, blank=True)
    documents = models.ManyToManyField(Document, blank=True, related_name="+")   # empty = search everything
    created_at = models.DateTimeField(auto_now_add=True)


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=[("user", "user"), ("assistant", "assistant")])
    content = models.TextField()
    citations = models.JSONField(default=list, blank=True)
    grounded = models.BooleanField(default=False)
    model = models.CharField(max_length=64, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class UsageCounter(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    metric = models.CharField(max_length=20)            # "questions" or "pages"
    period_start = models.DateField()
    used = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "metric", "period_start"], name="uniq_usage_period")]
