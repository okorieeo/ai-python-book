"""API tests for sharing. Each test names the acceptance criterion it protects (AC-n).

Assumes the Chapter 11 and 17 projects: chat.Conversation(public_id, user, title),
chat.Message(conversation, role, content, created_at) and a User model with public_id.
These tests need Django and DRF; run them with `python manage.py test sharing`.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditEvent
from chat.models import Conversation, Message
from sharing.models import SharedLink

User = get_user_model()
BASE = "/api/v1"


@override_settings(SHARE_PUBLIC_BASE_URL="https://app.example.com")
class ShareApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ada = User.objects.create_user(email="ada@example.com", password="pw-ada-12345")
        self.bob = User.objects.create_user(email="bob@example.com", password="pw-bob-12345")
        self.conv = Conversation.objects.create(user=self.ada, title="Rate limits explained")
        Message.objects.create(conversation=self.conv, role="user", content="What is a rate limit?")
        Message.objects.create(conversation=self.conv, role="assistant", content="A cap on requests.")
        self.api = APIClient()
        self.api.force_authenticate(self.ada)
        self.anon = APIClient()

    def share_url(self, conv=None):
        return f"{BASE}/conversations/{(conv or self.conv).public_id}/share/"

    def create(self, **body):
        return self.api.post(self.share_url(), body, format="json")

    def token_from(self, response) -> str:
        return response.json()["url"].rsplit("/", 1)[1]

    # AC-1
    def test_ac1_owner_creates_link_with_default_and_chosen_lifetime(self):
        r = self.create()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["state"], "active")
        link = SharedLink.objects.get(public_id=r.json()["id"])
        self.assertAlmostEqual((link.expires_at - timezone.now()).days, 6, delta=1)  # 7 days by default
        self.assertIsNone(SharedLink.objects.get(public_id=self.create(expires_in="never").json()["id"]).expires_at)
        self.assertEqual(self.create(expires_in="forever").status_code, 400)

    # AC-2
    def test_ac2_url_is_shown_once_and_only_the_hash_is_stored(self):
        created = self.create().json()
        self.assertIn("/s/", created["url"])
        listed = self.api.get(self.share_url()).json()
        self.assertNotIn("url", listed[0])
        token = created["url"].rsplit("/", 1)[1]
        self.assertNotEqual(SharedLink.objects.get().token_hash, token)

    # AC-3, AC-10
    def test_ac3_anyone_can_read_and_ac10_response_is_not_cached_or_indexed(self):
        token = self.token_from(self.create())
        r = self.anon.get(f"{BASE}/public/shared/{token}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([m["role"] for m in r.json()["messages"]], ["user", "assistant"])
        self.assertNotIn("user", r.json())
        self.assertEqual(r["Cache-Control"], "no-store")
        self.assertIn("noindex", r["X-Robots-Tag"])

    # AC-4
    def test_ac4_later_messages_are_not_visible(self):
        token = self.token_from(self.create())
        Message.objects.create(conversation=self.conv, role="user", content="secret follow-up",
                               created_at=timezone.now() + timedelta(seconds=5))
        contents = [m["content"] for m in self.anon.get(f"{BASE}/public/shared/{token}/").json()["messages"]]
        self.assertNotIn("secret follow-up", contents)

    # AC-5, AC-6
    def test_ac5_revoke_works_at_once_and_ac6_all_failures_look_the_same(self):
        created = self.create().json()
        token = created["url"].rsplit("/", 1)[1]
        self.assertEqual(self.api.delete(f"{self.share_url()}{created['id']}/").status_code, 204)
        revoked = self.anon.get(f"{BASE}/public/shared/{token}/")
        unknown = self.anon.get(f"{BASE}/public/shared/{'x' * 43}/")
        expired_token = self.token_from(self.create())
        SharedLink.objects.filter(revoked_at__isnull=True).update(expires_at=timezone.now() - timedelta(seconds=1))
        expired = self.anon.get(f"{BASE}/public/shared/{expired_token}/")
        for r in (revoked, unknown, expired):
            self.assertEqual(r.status_code, 404)
        self.assertEqual(revoked.content, unknown.content)
        self.assertEqual(unknown.content, expired.content)

    # AC-7
    def test_ac7_other_users_get_404(self):
        created = self.create().json()
        other = APIClient()
        other.force_authenticate(self.bob)
        self.assertEqual(other.post(self.share_url(), {}, format="json").status_code, 404)
        self.assertEqual(other.get(self.share_url()).status_code, 404)
        self.assertEqual(other.delete(f"{self.share_url()}{created['id']}/").status_code, 404)

    # AC-8
    def test_ac8_creation_is_limited_per_day(self):
        for _ in range(20):
            self.assertEqual(self.create().status_code, 201)
        r = self.create()
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r)

    # AC-9
    def test_ac9_create_and_revoke_are_audited_once_each(self):
        created = self.create().json()
        self.api.delete(f"{self.share_url()}{created['id']}/")
        self.api.delete(f"{self.share_url()}{created['id']}/")  # revoking twice adds nothing
        actions = list(AuditEvent.objects.order_by("id").values_list("action", flat=True))
        self.assertEqual(actions, ["share.link_created", "share.link_revoked"])

    # AC-12
    def test_ac12_deleting_a_conversation_deletes_its_links(self):
        self.create()
        self.conv.delete()
        self.assertEqual(SharedLink.objects.count(), 0)

    # AC-13
    def test_ac13_views_are_counted(self):
        created = self.create().json()
        token = created["url"].rsplit("/", 1)[1]
        for _ in range(3):
            self.anon.get(f"{BASE}/public/shared/{token}/")
        self.anon.get(f"{BASE}/public/shared/{'y' * 43}/")  # failed reads do not count
        self.assertEqual(self.api.get(self.share_url()).json()[0]["view_count"], 3)
