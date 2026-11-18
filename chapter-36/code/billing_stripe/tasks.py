from celery import shared_task
from django.core.management import call_command


@shared_task
def reconcile_all() -> None:
    """Nightly safety net: re-read every live subscription from Stripe and repair our copy."""
    call_command("stripe_reconcile")
