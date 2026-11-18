from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from audit.models import AuditEvent
from audit.services import Action, record
from chat import services
from chat.models import Conversation

User = get_user_model()
PASSWORD = "a-long-test-password"


class AuditTrailTests(TestCase):
    def setUp(self):
        self.ada = User.objects.create_user(email="ada@example.com", password=PASSWORD)
        self.bo = User.objects.create_user(email="bo@example.com", password=PASSWORD)
        self.conversation = services.create_conversation(user=self.ada, title="Plans")

    def test_record_stores_actor_target_and_request_context(self):
        request = RequestFactory().get(
            "/", HTTP_USER_AGENT="test-agent/1.0", REMOTE_ADDR="203.0.113.9"
        )
        request.user = self.ada
        event = record(
            Action.DATA_EXPORTED, request=request, target=self.conversation,
            metadata={"format": "json", "api_key": "sk_live_abcdefgh12345678"},
        )
        self.assertEqual(event.actor_id, self.ada.public_id)
        self.assertEqual(event.target_type, "conversation")
        self.assertEqual(event.target_id, str(self.conversation.public_id))
        self.assertEqual(event.ip_address, "203.0.113.9")
        self.assertEqual(event.user_agent, "test-agent/1.0")
        self.assertEqual(event.metadata["format"], "json")
        self.assertEqual(event.metadata["api_key"], "[REDACTED]")  # not stored

    def test_events_cannot_be_changed_or_deleted(self):
        event = record(Action.LOGIN_FAILED, metadata={"reason": "bad password"})
        event.action = "something.else"
        with self.assertRaises(PermissionError):
            event.save()
        with self.assertRaises(PermissionError):
            event.delete()
        stored = AuditEvent.objects.get(pk=event.pk)
        self.assertEqual(stored.action, "auth.login_failed")

    def test_deleting_a_conversation_leaves_an_audit_event(self):
        public_id = self.conversation.public_id
        services.delete_conversation(user=self.ada, conversation=self.conversation)
        self.assertFalse(Conversation.objects.filter(public_id=public_id).exists())
        event = AuditEvent.objects.get(action=Action.CONVERSATION_DELETED)
        self.assertEqual(event.actor_id, self.ada.public_id)
        self.assertEqual(event.target_id, str(public_id))

    def test_someone_elses_conversation_is_neither_deleted_nor_audited(self):
        with self.assertRaises(Conversation.DoesNotExist):
            services.delete_conversation(user=self.bo, conversation=self.conversation)
        self.assertTrue(Conversation.objects.filter(pk=self.conversation.pk).exists())
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_audit_event_survives_deleting_the_user(self):
        record(Action.LOGIN_SUCCEEDED, actor=self.bo)
        self.bo.delete()
        events = AuditEvent.objects.filter(action=Action.LOGIN_SUCCEEDED)
        self.assertEqual(events.count(), 1)
