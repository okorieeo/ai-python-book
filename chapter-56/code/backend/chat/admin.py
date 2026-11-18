from django.contrib import admin

from .models import Conversation, UsageDay


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "updated_at")
    search_fields = ("user__email",)
    # no message content columns: staff do not browse private conversations by default (Chapter 34)


@admin.register(UsageDay)
class UsageDayAdmin(admin.ModelAdmin):
    list_display = ("user", "day", "messages", "input_tokens", "output_tokens")
    list_filter = ("day",)
