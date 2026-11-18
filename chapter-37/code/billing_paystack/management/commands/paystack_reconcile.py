from django.core.management.base import BaseCommand

from paystackbilling.service import User as BillingUser
from paystackbilling.handlers import sync_subscription

from billing_paystack.models import PaystackSubscription
from billing_paystack.services import get_config, get_gateway
from billing_paystack.store import DjangoBillingStore


class Command(BaseCommand):
    help = "Re-read every unfinished subscription from Paystack and repair our copy. Run it nightly."

    def handle(self, *args, **options):
        import time
        store, gateway, config, checked, repaired = DjangoBillingStore(), get_gateway(), get_config(), 0, 0
        for row in PaystackSubscription.objects.exclude(status__in=["cancelled", "completed"]):
            before = store.subscription_for(row.user_id)
            sync_subscription(store, config, gateway, row.subscription_code, time.time(), str(row.user_id))
            checked += 1
            repaired += before != store.subscription_for(row.user_id)
        self.stdout.write(f"checked {checked} subscriptions, repaired {repaired}")
