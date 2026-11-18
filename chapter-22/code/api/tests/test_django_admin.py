from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from chat.models import Conversation, Document

FAST = ["django.contrib.auth.hashers.MD5PasswordHasher"]

@override_settings(PASSWORD_HASHERS=FAST)
class DjangoAdminTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser("boss", "b@example.com", "pw-1")
        self.client.force_login(self.boss)
        self.ada = User.objects.create_user("ada", "a@example.com", "pw-1")

    def test_every_list_page_loads(self):
        for model in ("accounts_user", "chat_conversation", "chat_message",
                      "chat_document"):
            reply = self.client.get(reverse(f"admin:{model}_changelist"))
            self.assertEqual(reply.status_code, 200, model)

    def test_restore_action_undeletes_conversations(self):
        chat = Conversation.objects.create(user=self.ada, title="x",
                                           deleted_at=timezone.now())
        self.client.post(reverse("admin:chat_conversation_changelist"), {
            "action": "restore_conversations", "_selected_action": [chat.pk]})
        chat.refresh_from_db()
        self.assertIsNone(chat.deleted_at)

    def test_reprocess_action_queues_documents(self):
        doc = Document.objects.create(user=self.ada, filename="a.pdf",
                                      status="failed", error="boom")
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.client.post(reverse("admin:chat_document_changelist"), {
                "action": "reprocess", "_selected_action": [doc.pk]})
        doc.refresh_from_db()
        self.assertEqual((doc.status, doc.error, len(callbacks)),
                         ("processing", "", 1))

    def test_ordinary_members_cannot_enter_the_admin(self):
        self.client.force_login(self.ada)
        reply = self.client.get(reverse("admin:index"))
        self.assertEqual(reply.status_code, 302)               # sent to log in
