from celery import shared_task
from django.apps import apps
from django.utils import timezone

from core.responsible.retention import RULES, batched, cutoff

from .models import DeletionRequest
from .services import execute_deletion


@shared_task
def run_due_deletions() -> int:
    """Beat: hourly. Picks up scheduled requests whose grace period ended, and retries partial ones."""
    due = DeletionRequest.objects.filter(
        status__in=[DeletionRequest.Status.SCHEDULED, DeletionRequest.Status.PARTIAL],
        scheduled_for__lte=timezone.now())
    count = 0
    for deletion in due:
        execute_deletion(deletion)
        count += 1
    return count


@shared_task
def purge_expired(model_label: str, rule_name: str) -> int:
    """Beat: daily, e.g. purge_expired('chat.AIRequestLog', 'ai_request_logs')."""
    rule = RULES[rule_name]
    if rule.days is None:
        return 0
    model = apps.get_model(model_label)
    ids = list(model.objects.filter(created_at__lte=cutoff(timezone.now(), rule.days)).values_list("pk", flat=True))
    deleted = 0
    for chunk in batched(ids, 500):
        deleted += model.objects.filter(pk__in=chunk).delete()[0]
    return deleted
