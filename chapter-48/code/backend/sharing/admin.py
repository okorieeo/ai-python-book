from django.contrib import admin

from .models import SharedLink


@admin.register(SharedLink)
class SharedLinkAdmin(admin.ModelAdmin):
    list_display = ("public_id", "created_by", "conversation", "created_at", "expires_at", "revoked_at", "view_count")
    readonly_fields = [f.name for f in SharedLink._meta.fields]  # the hash must not be editable or copied around

    def has_add_permission(self, request):
        return False
