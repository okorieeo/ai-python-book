import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from rest_framework.test import APITestCase

from chat import services
from chat.models import Message

User = get_user_model()
PASSWORD = "a-long-test-password"


class IdempotentSendTests(APITestCase):
    def setUp(self):
        self.ada = User.objects.create_user(email="ada@example.com", password=PASSWORD)
        self.bo = User.objects.create_user(email="bo@example.com", password=PASSWORD)
        self.conversation = services.create_conversation(user=self.ada, title="Plans")
        # Adjust to the URL layout of your Chapter 12 router.
        self.url = f"/api/v1/conversations/{self.conversation.public_id}/messages/"
        self.client.force_authenticate(self.ada)

    def send(self, client_id, content="hello"):
        return self.client.post(self.url, {"client_id": str(client_id), "content": content}, format="json")

    def test_first_send_creates_the_message(self):
        client_id = uuid.uuid4()
        response = self.send(client_id)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(str(response.data["client_id"]), str(client_id))
        self.assertEqual(Message.objects.count(), 1)

    def test_a_retry_returns_the_same_message_and_creates_nothing(self):
        client_id = uuid.uuid4()
        first = self.send(client_id)
        second = self.send(client_id)
        third = self.send(client_id)
        self.assertEqual((first.status_code, second.status_code, third.status_code), (201, 200, 200))
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Message.objects.count(), 1)

    def test_same_client_id_with_different_content_is_rejected(self):
        client_id = uuid.uuid4()
        self.send(client_id, "original")
        response = self.send(client_id, "something else")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Message.objects.get().content, "original")

    def test_different_client_ids_are_different_messages(self):
        self.send(uuid.uuid4(), "one")
        self.send(uuid.uuid4(), "one")  # same words twice is allowed
        self.assertEqual(Message.objects.count(), 2)

    def test_clients_without_a_client_id_still_work(self):
        self.client.post(self.url, {"content": "from the web"}, format="json")
        self.client.post(self.url, {"content": "from the web"}, format="json")
        self.assertEqual(Message.objects.filter(client_id__isnull=True).count(), 2)

    def test_a_race_between_two_copies_ends_with_one_message(self):
        """Copy A passes the 'already stored?' check, then copy B stores the message first."""
        client_id = uuid.uuid4()
        winner = Message.objects.create(conversation=self.conversation, role="user", content="hello", client_id=client_id)
        real_find = services._find_by_client_id
        looks = []

        def find(conversation, cid):
            looks.append(cid)
            return None if len(looks) == 1 else real_find(conversation, cid)  # first look: "not stored yet"

        with mock.patch.object(services, "_find_by_client_id", side_effect=find):
            message, created = services.create_user_message(
                user=self.ada, conversation=self.conversation, content="hello", client_id=client_id
            )
        self.assertEqual(len(looks), 2)  # it looked, failed to insert, then looked again
        self.assertFalse(created)
        self.assertEqual(message.pk, winner.pk)
        self.assertEqual(Message.objects.count(), 1)

    def test_an_unrelated_integrity_error_is_not_swallowed(self):
        with mock.patch.object(Message.objects, "create", side_effect=IntegrityError("something else")):
            with self.assertRaises(IntegrityError):
                services.create_user_message(
                    user=self.ada, conversation=self.conversation, content="x", client_id=uuid.uuid4()
                )

    def test_someone_elses_conversation_is_a_404_even_with_a_valid_client_id(self):
        self.client.force_authenticate(self.bo)
        response = self.send(uuid.uuid4())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Message.objects.count(), 0)

    def test_the_same_client_id_in_two_conversations_does_not_clash(self):
        other = services.create_conversation(user=self.ada, title="Other")
        client_id = uuid.uuid4()
        self.send(client_id)
        response = self.client.post(
            f"/api/v1/conversations/{other.public_id}/messages/", {"client_id": str(client_id), "content": "hello"}, format="json"
        )
        self.assertEqual(response.status_code, 201)

    def test_bad_input_is_a_400(self):
        self.assertEqual(self.client.post(self.url, {"client_id": "not-a-uuid", "content": "x"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(self.url, {"client_id": str(uuid.uuid4()), "content": "   "}, format="json").status_code, 400)
        self.assertEqual(self.client.post(self.url, {"client_id": str(uuid.uuid4()), "content": "x" * 8001}, format="json").status_code, 400)

    def test_anonymous_requests_are_rejected(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.send(uuid.uuid4()).status_code, (401, 403))
