from django.core.management.base import BaseCommand

from billing.seed import seed_default_plans


class Command(BaseCommand):
    help = "Create or update the default plans, prices and entitlements."

    def handle(self, *args, **options):
        plans = seed_default_plans()
        self.stdout.write(self.style.SUCCESS(f"Seeded plans: {', '.join(p.code for p in plans)}"))
