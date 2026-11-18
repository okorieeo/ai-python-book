from django.contrib import admin

from .models import Discrepancy, Invoice, Payment, ReconciliationRun, Refund, WebhookEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "provider", "status", "amount_minor", "currency", "created_at")
    list_filter = ("provider", "status", "currency")
    search_fields = ("reference", "provider_ref")
    readonly_fields = [f.name for f in Payment._meta.fields]      # money moves through code paths, not admin edits

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "event_id", "raw_type", "outcome", "received_at")
    list_filter = ("provider", "outcome")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "kind", "gross_minor", "currency", "issued_at")
    readonly_fields = [f.name for f in Invoice._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register([Refund, ReconciliationRun, Discrepancy])
