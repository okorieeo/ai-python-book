from django.contrib import admin

from .models import PromptRun


@admin.register(PromptRun)
class PromptRunAdmin(admin.ModelAdmin):
    list_display = ("created_at", "prompt_id", "model", "input_tokens", "output_tokens",
                    "attempts", "injection_risk", "output_flagged")
    list_filter = ("injection_risk", "output_flagged", "model")
    search_fields = ("prompt_id",)
    readonly_fields = [f.name for f in PromptRun._meta.fields]
