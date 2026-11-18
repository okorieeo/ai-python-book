import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from chat.models import Conversation, Document, Message, UsageRecord

class Command(BaseCommand):
    help = "Create demo users and months of usage so the dashboard has data."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=40)
        parser.add_argument("--days", type=int, default=90)

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(42)                   # same data for the same day
        now, days = timezone.now(), options["days"]
        User.objects.filter(username__startswith="demo_").delete()

        staff = [("demo_admin", "admin"), ("demo_support", "support")]
        for name, role in staff:
            User.objects.create_user(name, f"{name}@example.com",
                                     "demo-pass-1", role=role)
        members = [
            User.objects.create_user(
                f"demo_user{n:02d}", f"user{n:02d}@example.com", "demo-pass-1",
                date_joined=now - timedelta(days=rng.randint(0, days - 1)))
            for n in range(options["users"])
        ]

        usage, chats, docs = [], [], []
        for user in members:
            activity = rng.choice([0.2, 0.5, 0.8])         # light to heavy user
            for back in range(days - 1, -1, -1):
                day = now - timedelta(days=back)
                if day < user.date_joined:
                    continue
                busy = 0.35 if day.weekday() >= 5 else 0.75   # quieter weekends
                if rng.random() < activity * busy:
                    for _ in range(rng.randint(1, 6)):
                        usage.append(UsageRecord(
                            user=user, input_tokens=rng.randint(200, 2500),
                            output_tokens=rng.randint(100, 1800)))
                        usage[-1].when = day - timedelta(
                            minutes=rng.randint(0, 1000))
            for n in range(rng.randint(1, 4)):
                chats.append(Conversation(user=user, title=f"Chat {n + 1}"))
            for n in range(rng.choice([0, 0, 1, 2, 3])):
                docs.append(Document(
                    user=user, filename=f"file{n + 1}.pdf",
                    status=rng.choices(Document.Status.values,
                                       weights=[1, 2, 14, 3])[0]))

        UsageRecord.objects.bulk_create(usage)
        for record in usage:
            record.created_at = max(record.when, record.user.date_joined)
        UsageRecord.objects.bulk_update(usage, ["created_at"], batch_size=500)
        Conversation.objects.bulk_create(chats)
        Document.objects.bulk_create(docs)

        messages = []
        for chat in chats:
            for n in range(rng.randint(2, 6)):
                messages.append(Message(
                    conversation=chat, content=f"Message {n + 1}",
                    role="user" if n % 2 == 0 else "assistant"))
        Message.objects.bulk_create(messages)
        for message in messages:                  # spread over the period
            message.created_at = now - timedelta(
                days=rng.randint(0, days - 1), minutes=rng.randint(0, 1000))
        Message.objects.bulk_update(messages, ["created_at"], batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f"Created {len(members) + len(staff)} users, {len(chats)} "
            f"conversations, {len(messages)} messages,\n{len(usage)} usage "
            f"records and {len(docs)} documents."))
