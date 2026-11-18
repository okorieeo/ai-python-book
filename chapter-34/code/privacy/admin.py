from django.contrib import admin

from .models import ConsentEvent, DeletionRequest, LegalDocument


@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ("kind", "version", "effective_at", "sha256")


@admin.register(ConsentEvent)
class ConsentEventAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "granted", "document_version", "created_at")
    list_filter = ("purpose", "granted")

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


@admin.register(DeletionRequest)
class DeletionRequestAdmin(admin.ModelAdmin):
    list_display = ("public_id", "status", "scheduled_for", "completed_at")
    readonly_fields = [f.name for f in DeletionRequest._meta.fields]
