from django.contrib import admin

from .models import Plan, Subscription, WebhookEvent


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "daily_message_limit", "price_usd_cents", "is_public")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "gateway", "current_period_end", "cancel_at_period_end")
    search_fields = ("user__email", "external_customer_id", "external_subscription_id")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "event_type", "event_id", "outcome", "received_at")
    list_filter = ("provider", "outcome")
    readonly_fields = [f.name for f in WebhookEvent._meta.fields]  # an event log should not be editable
