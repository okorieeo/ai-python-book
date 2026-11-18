from django.contrib import admin, messages

from . import services
from .models import Conversation, Document, Message

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "message_count", "updated_at", "is_deleted")
    list_filter = ("deleted_at",)
    search_fields = ("title", "user__username", "user__email")
    list_select_related = ("user",)               # no N+1 in the list
    raw_id_fields = ("user",)                     # no giant dropdown
    readonly_fields = ("public_id", "message_count", "created_at", "updated_at")
    actions = ["restore_conversations"]

    @admin.display(boolean=True, description="Deleted")
    def is_deleted(self, obj):
        return obj.deleted_at is not None

    @admin.action(description="Restore the selected (soft-deleted) conversations")
    def restore_conversations(self, request, queryset):
        count = queryset.filter(deleted_at__isnull=False).update(deleted_at=None)
        self.message_user(request, f"Restored {count} conversation(s).",
                          messages.SUCCESS)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "role", "created_at")
    list_filter = ("role",)
    raw_id_fields = ("conversation",)
    list_select_related = ("conversation",)
    readonly_fields = ("public_id", "created_at")

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("filename", "user", "status", "chunk_count", "created_at")
    list_filter = ("status",)
    search_fields = ("filename", "user__username")
    list_select_related = ("user",)
    raw_id_fields = ("user",)
    readonly_fields = ("public_id", "chunk_count", "error", "created_at")
    actions = ["reprocess"]

    @admin.action(description="Process the selected documents again")
    def reprocess(self, request, queryset):
        for document in queryset:
            services.start_ingestion(document)
        self.message_user(request, f"Queued {queryset.count()} document(s).",
                          messages.SUCCESS)
