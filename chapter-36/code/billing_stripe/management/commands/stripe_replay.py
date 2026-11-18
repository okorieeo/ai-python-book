from django.conf import settings
from django.core.management.base import BaseCommand

from stripebilling.gateway import StripeGateway

from billing_stripe.services import get_processor


class Command(BaseCommand):
    help = "Fetch one event from Stripe by id and run it through our handlers (after you fixed a bug)."

    def add_arguments(self, parser):
        parser.add_argument("event_id")

    def handle(self, event_id, **options):
        event = StripeGateway(settings.STRIPE_SECRET_KEY).retrieve_event(event_id)   # authentic: fetched with our key
        result = get_processor().process_verified(event)
        self.stdout.write(f"{event_id}: HTTP {result.status} {result.outcome}")
