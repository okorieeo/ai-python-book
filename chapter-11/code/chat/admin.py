from django.contrib import admin

from .models import Conversation, Message, UsageRecord

class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ("role", "content", "model_name", "input_tokens", "output_tokens", "created_at")
    readonly_fields = ("created_at",)
    show_change_link = True

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("title", "user__email")
    raw_id_fields = ("user",)               # avoids a huge dropdown when there are many users
    readonly_fields = ("public_id", "created_at", "updated_at")
    inlines = [MessageInline]

@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "input_tokens", "output_tokens", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__email",)
    raw_id_fields = ("user", "message")
    date_hierarchy = "created_at"

    # The ledger is append-only: nobody edits history in the admin
    def has_change_permission(self, request, obj=None):
        return False
