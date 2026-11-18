from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from chat import services

User = get_user_model()
BASE = "/api/v1/conversations"  # adjust to the URL layout of your Chapter 12 router
PASSWORD = "a-long-test-password"


class CrossUserAccessTests(APITestCase):
    def setUp(self):
        self.ada = User.objects.create_user(email="ada@example.com", password=PASSWORD)
        self.bo = User.objects.create_user(email="bo@example.com", password=PASSWORD)
        self.conversation = services.create_conversation(user=self.ada, title="Plans")
        self.url = f"{BASE}/{self.conversation.public_id}/"

    def test_anonymous_requests_are_rejected(self):
        self.assertEqual(self.client.get(BASE).status_code, 401)

    def test_other_users_get_404_not_403_for_someone_elses_object(self):
        self.client.force_authenticate(self.bo)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)  # 403 would confirm it exists

    def test_lists_never_contain_other_users_objects(self):
        self.client.force_authenticate(self.bo)
        response = self.client.get(BASE)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Plans", response.content.decode())

    def test_other_users_cannot_modify_or_delete(self):
        self.client.force_authenticate(self.bo)
        patch = self.client.patch(self.url, {"title": "Hacked"}, format="json")
        self.assertEqual(patch.status_code, 404)
        self.assertEqual(self.client.delete(self.url).status_code, 404)
