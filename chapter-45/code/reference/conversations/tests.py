"""Endpoint tests that ship WITH the endpoint. Needs Django, DRF and a database (not executed while writing the book)."""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from core.chat.memory import EchoProvider

from .models import Conversation, Message

User = get_user_model()


class ConversationApiTests(APITestCase):
    def setUp(self):
        self.ada = User.objects.create_user(email="ada@example.com", password="a-long-test-password", role="member")
        self.bo = User.objects.create_user(email="bo@example.com", password="a-long-test-password", role="member")
        self.viewer = User.objects.create_user(email="v@example.com", password="a-long-test-password", role="viewer")
        self.conv = Conversation.objects.create(user=self.ada, title="Plan")
        self.url = f"/api/v1/conversations/{self.conv.public_id}/"

    # 1. authentication
    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/v1/conversations/").status_code, 401)

    # 2. ownership: another user's object is a 404, not a 403
    def test_other_users_conversation_is_404(self):
        self.client.force_authenticate(self.bo)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(self.url + "messages/").status_code, 404)
        self.assertEqual(self.client.delete(self.url).status_code, 404)

    # 3. the list contains only my data
    def test_list_is_scoped(self):
        Conversation.objects.create(user=self.bo, title="Secret")
        self.client.force_authenticate(self.ada)
        titles = [c["title"] for c in self.client.get("/api/v1/conversations/").json()["results"]]
        self.assertEqual(titles, ["Plan"])

    # 4. roles: a viewer can read but not create
    def test_viewer_cannot_create(self):
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.post("/api/v1/conversations/", {"title": "x"}, format="json").status_code, 403)

    # 5. no internal ids leak
    def test_ids_are_public_ids(self):
        self.client.force_authenticate(self.ada)
        body = self.client.get(self.url).json()
        self.assertIn("public_id", body)
        self.assertNotIn("id", body)
        self.assertNotIn("user", body)

    # 6. query count does not grow with the data
    def test_list_uses_a_constant_number_of_queries(self):
        for i in range(10):
            c = Conversation.objects.create(user=self.ada, title=f"c{i}")
            Message.objects.create(conversation=c, role="user", content="hi")
        self.client.force_authenticate(self.ada)
        with self.assertNumQueries(3):                       # session/user lookup aside: count, page, prefetch (adjust to your setup)
            self.client.get("/api/v1/conversations/")

    # 7. validation and idempotency on sending
    def test_send_requires_key_and_content(self):
        self.client.force_authenticate(self.ada)
        self.assertEqual(self.client.post(self.url + "send/", {"content": ""}, format="json").status_code, 400)
        r = self.client.post(self.url + "send/", {"content": "hello"}, format="json")
        self.assertEqual(r.status_code, 400)                  # no Idempotency-Key header

    def test_mass_assignment_is_ignored(self):
        self.client.force_authenticate(self.ada)
        r = self.client.post("/api/v1/conversations/", {"title": "ok", "user": self.bo.pk, "public_id": "x"}, format="json")
        self.assertEqual(r.status_code, 201)
        created = Conversation.objects.get(public_id=r.json()["public_id"])
        self.assertEqual(created.user, self.ada)
