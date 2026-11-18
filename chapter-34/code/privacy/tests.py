from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from chat import services as chat_services
from core.responsible.consent_logic import Purpose
from privacy import services
from privacy.models import ConsentEvent, DeletionRequest, LegalDocument

User = get_user_model()
PASSWORD = "a-long-test-password"


class ConsentServiceTests(TestCase):
    def setUp(self):
        self.ada = User.objects.create_user(email="ada@example.com", password=PASSWORD)

    def test_no_consent_until_granted_and_withdrawal_wins(self):
        self.assertFalse(services.user_has_consent(self.ada, Purpose.IMPROVEMENT))
        services.record_consent(user=self.ada, purpose=Purpose.IMPROVEMENT, granted=True, version="v1")
        self.assertTrue(services.user_has_consent(self.ada, Purpose.IMPROVEMENT))
        services.record_consent(user=self.ada, purpose=Purpose.IMPROVEMENT, granted=False, version="v1")
        self.assertFalse(services.user_has_consent(self.ada, Purpose.IMPROVEMENT))
        self.assertEqual(ConsentEvent.objects.filter(user=self.ada).count(), 2)   # history kept

    def test_events_cannot_be_edited(self):
        event = services.record_consent(user=self.ada, purpose=Purpose.ANALYTICS, granted=True, version="v1")
        event.granted = False
        with self.assertRaises(PermissionError):
            event.save()

    def test_required_documents_cannot_be_withdrawn(self):
        with self.assertRaises(ValueError):
            services.record_consent(user=self.ada, purpose=Purpose.TERMS, granted=False, version="v1")

    def test_new_document_version_requires_reacceptance(self):
        for kind in ("terms", "privacy"):
            LegalDocument.objects.create(kind=kind, version="2026-11", effective_at="2026-11-01T00:00Z",
                                         sha256="0" * 64, url="https://example.com/x")
        self.assertEqual(set(services.documents_to_accept(self.ada)), {Purpose.TERMS, Purpose.PRIVACY_NOTICE})


class ExportAndDeletionTests(APITestCase):
    def setUp(self):
        self.ada = User.objects.create_user(email="ada@example.com", password=PASSWORD)
        self.bo = User.objects.create_user(email="bo@example.com", password=PASSWORD)
        chat_services.create_conversation(user=self.ada, title="Ada private plan")
        chat_services.create_conversation(user=self.bo, title="Bo private plan")

    def test_export_needs_the_password_and_contains_only_my_data(self):
        self.client.force_authenticate(self.ada)
        self.assertEqual(self.client.post("/api/v1/privacy/export/", {"password": "wrong"}).status_code, 403)
        response = self.client.post("/api/v1/privacy/export/", {"password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        import io, zipfile
        text = zipfile.ZipFile(io.BytesIO(response.content)).read("data.json").decode()
        self.assertIn("Ada private plan", text)
        self.assertNotIn("Bo private plan", text)
        self.assertNotIn("pbkdf2", text)

    def test_deletion_is_scheduled_then_executed_and_leaves_other_users_alone(self):
        self.client.force_authenticate(self.ada)
        response = self.client.post("/api/v1/privacy/delete/", {"password": PASSWORD, "confirm": "DELETE"})
        self.assertEqual(response.status_code, 202)
        self.ada.refresh_from_db()
        self.assertFalse(self.ada.is_active)
        deletion = DeletionRequest.objects.get(user_public_id=self.ada.public_id)
        services.execute_deletion(deletion)
        deletion.refresh_from_db()
        self.assertEqual(deletion.status, DeletionRequest.Status.COMPLETE)
        self.assertFalse(User.objects.filter(email="ada@example.com").exists())
        self.assertTrue(User.objects.filter(email="bo@example.com").exists())
        self.assertEqual(self.bo.conversations.count(), 1)

    def test_cancelling_reactivates_the_account(self):
        services.request_account_deletion(user=self.ada)
        self.assertTrue(services.cancel_account_deletion(user=self.ada))
        self.ada.refresh_from_db()
        self.assertTrue(self.ada.is_active)

    def test_every_model_with_personal_data_is_in_the_inventory(self):
        from django.apps import apps
        from core.responsible.data_inventory import INVENTORY
        listed = {".".join(item.key.split(".")[:2]) for item in INVENTORY}
        tracked_apps = {"users", "chat", "billing", "privacy", "rag"}
        ignore = {"privacy.LegalDocument", "privacy.DeletionRequest", "chat.Conversation"}   # keyed elsewhere
        missing = [m._meta.label for m in apps.get_models()
                   if m._meta.app_label in tracked_apps and m._meta.label not in listed | ignore]
        self.assertEqual(missing, [], "Add these models to core/responsible/data_inventory.py")
