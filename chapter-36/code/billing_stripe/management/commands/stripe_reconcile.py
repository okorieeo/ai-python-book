from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from stripebilling.service import User as BillingUser

from billing_stripe.models import StripeSubscription
from billing_stripe.services import get_service


class Command(BaseCommand):
    help = "Re-read every non-canceled subscription from Stripe and repair our copy. Run it nightly."

    def handle(self, *args, **options):
        service, repaired = get_service(), 0
        users = get_user_model().objects.filter(stripe_subscription__in=StripeSubscription.objects.exclude(status="canceled"))
        for user in users:
            before = service.store.subscription_for(str(user.pk))
            service.reconcile(BillingUser(str(user.pk), user.email))
            after = service.store.subscription_for(str(user.pk))
            repaired += before != after
        self.stdout.write(f"checked {users.count()} subscriptions, repaired {repaired}")
