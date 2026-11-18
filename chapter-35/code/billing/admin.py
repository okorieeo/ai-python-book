from django.contrib import admin

from . import models


class ReadOnlyAdmin(admin.ModelAdmin):
    """Records that describe what happened are looked at in the admin, never edited there."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PriceInline(admin.TabularInline):
    model = models.Price
    extra = 0


class EntitlementInline(admin.TabularInline):
    model = models.PlanEntitlement
    extra = 0


@admin.register(models.Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "tier", "is_public", "is_active")
    inlines = [PriceInline, EntitlementInline]


@admin.register(models.Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "plan",
        "status",
        "current_period_end",
        "cancel_at_period_end",
        "provider",
    )
    list_filter = ("status", "plan", "provider")
    readonly_fields = (
        "status",
        "current_period_start",
        "current_period_end",
        "billing_anchor",
        "period_number",
        "provider_subscription_id",
    )  # change status through the services


@admin.register(models.EntitlementOverride)
class OverrideAdmin(admin.ModelAdmin):
    list_display = ("user", "key", "enabled", "limit", "expires_at", "reason")


@admin.register(models.UsageEvent)
class UsageEventAdmin(ReadOnlyAdmin):
    list_display = ("user", "key", "quantity", "occurred_at", "cost_micro_usd")


@admin.register(models.Invoice)
class InvoiceAdmin(ReadOnlyAdmin):
    list_display = ("number", "user", "status", "currency", "total_minor", "issued_at")


@admin.register(models.Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = (
        "provider",
        "provider_payment_id",
        "invoice",
        "amount_minor",
        "currency",
        "status",
    )


@admin.register(models.WebhookEvent)
class WebhookEventAdmin(ReadOnlyAdmin):
    list_display = ("provider", "event_id", "event_type", "status", "received_at")
