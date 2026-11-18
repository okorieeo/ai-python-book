from django.contrib import admin

from .models import KnowledgeChunk, KnowledgeDocument


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "status", "chunk_count", "created_at")
    list_filter = ("status",)
    readonly_fields = ("content_hash", "chunk_count", "error")


@admin.register(KnowledgeChunk)
class KnowledgeChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "index", "injection_risk", "embedding_model")
    list_filter = ("injection_risk", "embedding_model")
    exclude = ("embedding", "search_vector")      # large and unreadable in a form
    readonly_fields = [f.name for f in KnowledgeChunk._meta.fields if f.name not in {"embedding", "search_vector"}]
