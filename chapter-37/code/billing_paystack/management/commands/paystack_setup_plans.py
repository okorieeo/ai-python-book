from django.conf import settings
from django.core.management.base import BaseCommand

from paystackbilling.money import to_subunit

from billing_paystack.services import get_gateway


class Command(BaseCommand):
    help = "Create the recurring plans from settings.PAYSTACK_PLANS at Paystack (test mode first) and print their codes."

    def handle(self, *args, **options):
        gateway = get_gateway()
        for key, v in settings.PAYSTACK_PLANS.items():
            if v["interval"] == "once" or v.get("plan_code"):
                continue
            made = gateway.create_plan({"name": key, "interval": v["interval"], "currency": v["currency"],
                                        "amount": to_subunit(v["amount"], v["currency"])})
            self.stdout.write(f"{key}: plan_code={made['plan_code']}   <- put this in the settings")
