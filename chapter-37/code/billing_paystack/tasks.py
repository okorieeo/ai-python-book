from celery import shared_task

from .services import get_service


@shared_task
def reconcile_pending_payments() -> dict:
    """Every few minutes: re-verify payments still pending after 15 minutes (the callback and the webhook both
    got lost). Schedule it with Celery beat."""
    return get_service().reconcile_pending()


@shared_task
def reconcile_subscriptions() -> None:
    """Nightly: re-read every unfinished subscription from Paystack and repair our copy."""
    from django.core.management import call_command
    call_command("paystack_reconcile")
