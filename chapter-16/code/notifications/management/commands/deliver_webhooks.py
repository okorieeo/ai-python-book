from django.core.management.base import BaseCommand

from notifications.outbound import deliver_due


class Command(BaseCommand):
    help = "Send every outbound webhook that is due. Run it every minute."

    def handle(self, *args, **options):
        succeeded = deliver_due()
        self.stdout.write(f"{succeeded} webhook(s) delivered")
