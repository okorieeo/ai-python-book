from django.contrib import admin

from .models import (CreditGrant, PaystackCustomer, PaystackPayment, PaystackSubscription, PendingTransaction,
                     WebhookEvent)


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event_type", "status", "attempts")
    list_filter = ("status", "event_type")
    readonly_fields = [f.name for f in WebhookEvent._meta.fields]


@admin.register(PaystackSubscription)
class PaystackSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "tier", "plan_key", "next_payment_date")
    list_filter = ("status", "tier")
    exclude = ("email_token", "authorization_code")      # never show secrets in the admin


@admin.register(PendingTransaction)
class PendingTransactionAdmin(admin.ModelAdmin):
    list_display = ("reference", "user", "kind", "amount", "currency", "status")
    list_filter = ("status", "kind")


admin.site.register([PaystackCustomer, PaystackPayment, CreditGrant])
