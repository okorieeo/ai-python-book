from django.contrib import admin

from .models import CreditGrant, StripeCustomer, StripePayment, StripeSubscription, WebhookEvent


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event_id", "event_type", "status", "attempts")
    list_filter = ("status", "event_type")
    search_fields = ("event_id",)
    readonly_fields = [f.name for f in WebhookEvent._meta.fields]


@admin.register(StripeSubscription)
class StripeSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "tier", "plan_key", "cancel_at_period_end")
    list_filter = ("status", "tier")
    search_fields = ("subscription_id", "customer_id")


admin.site.register([StripeCustomer, StripePayment, CreditGrant])
