from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    """A read-only window on the audit trail: no one can add, edit or delete here."""

    list_display = (
        "created_at", "action", "actor_id", "target_type", "target_id",
        "ip_address", "request_id",
    )
    list_filter = ("action",)
    search_fields = ("actor_id", "target_id", "request_id", "ip_address")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
