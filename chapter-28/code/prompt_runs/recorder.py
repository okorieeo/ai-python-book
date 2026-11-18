from .models import PromptRun


def django_recorder(record: dict) -> PromptRun:
    """Pass this to run_prompt(..., recorder=django_recorder)."""
    return PromptRun.objects.create(**record)
