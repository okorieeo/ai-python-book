import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from . import services
from .models import Conversation, Message, UsageRecord

User = get_user_model()

class ChatServiceTests(TestCase):
    def setUp(self):
        self.ada = User.objects.create_user(email="ada@example.com", password="a-long-test-password")
        self.bo = User.objects.create_user(email="bo@example.com", password="a-long-test-password")

    def test_create_conversation_uses_default_title(self):
        conversation = services.create_conversation(user=self.ada, title="   ")
        self.assertEqual(conversation.title, "New conversation")

    def test_title_too_long_is_rejected(self):
        with self.assertRaises(ValueError):
            services.create_conversation(user=self.ada, title="x" * 201)

    def test_user_cannot_read_someone_elses_conversation(self):
        conversation = services.create_conversation(user=self.ada, title="Private")
        with self.assertRaises(Conversation.DoesNotExist):
            services.get_conversation_for_user(user=self.bo, public_id=conversation.public_id)
        with self.assertRaises(Conversation.DoesNotExist):
            services.get_conversation_for_user(user=self.ada, public_id=uuid.uuid4())

    def test_empty_message_is_rejected(self):
        conversation = services.create_conversation(user=self.ada)
        with self.assertRaises(ValueError):
            services.add_user_message(conversation=conversation, content="   ")
        self.assertEqual(Message.objects.count(), 0)

    def test_assistant_reply_creates_message_and_usage_together(self):
        conversation = services.create_conversation(user=self.ada)
        message = services.save_assistant_reply(
            conversation=conversation, text="Hello!", input_tokens=60, output_tokens=40, model_name="test-model",
        )
        self.assertEqual(message.role, "assistant")
        self.assertEqual(UsageRecord.objects.filter(user=self.ada).count(), 1)
        self.assertEqual(services.tokens_used_this_month(user=self.ada), 100)

    def test_usage_ignores_previous_months_and_other_users(self):
        conversation = services.create_conversation(user=self.ada)
        services.save_assistant_reply(conversation=conversation, text="a", input_tokens=10, output_tokens=5, model_name="m")
        old = UsageRecord.objects.create(user=self.ada, input_tokens=1000, output_tokens=1000)
        UsageRecord.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=40))
        UsageRecord.objects.create(user=self.bo, input_tokens=500, output_tokens=500)
        self.assertEqual(services.tokens_used_this_month(user=self.ada), 15)

    def test_usage_is_a_single_query(self):
        with self.assertNumQueries(1):
            services.tokens_used_this_month(user=self.ada)
