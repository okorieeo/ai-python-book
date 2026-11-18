"""Needs Django, DRF and a test database, so it was NOT run while writing this chapter. Run it in your project."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from rest_framework_simplejwt.tokens import AccessToken   # adapt to the auth library from Chapter 13

from chat.models import Conversation

from .dto import TextDelta, TurnFinished, TurnStarted
from .errors import AIBudgetExceeded


def auth_header(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(user)}"}


class ChatStreamViewTests(TransactionTestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="alice", password="x")
        self.bob = User.objects.create_user(username="bob", password="x")
        self.conv = Conversation.objects.create(user=self.alice)
        self.url = f"/api/v1/conversations/{self.conv.pk}/stream/"

    def post(self, user, body, **extra):
        return self.client.post(self.url, data=json.dumps(body), content_type="application/json",
                                **(auth_header(user) if user else {}), **extra)

    def test_anonymous_gets_401(self):
        self.assertEqual(self.post(None, {"text": "hi"}).status_code, 401)

    def test_bad_body_is_400(self):
        self.assertEqual(self.post(self.alice, {"nope": 1}).status_code, 400)
        self.assertEqual(self.post(self.alice, {"text": 123}).status_code, 400)

    def test_someone_elses_conversation_is_404_not_403(self):
        self.assertEqual(self.post(self.bob, {"text": "hi"}).status_code, 404)

    def test_budget_exceeded_is_a_real_429_with_retry_after(self):
        async def refuse(**kwargs):          # fails on the first step, before any event is produced
            raise AIBudgetExceeded(retry_after=3600)
            yield  # pragma: no cover

        with mock.patch("ai.views.get_chat_service", return_value=mock.Mock(stream_reply=refuse)):
            res = self.post(self.alice, {"text": "hi"})
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res["Retry-After"], "3600")
        self.assertEqual(res.json()["code"], "budget_exceeded")

    def test_the_stream_has_the_right_headers_and_events(self):
        async def fake_stream_reply(**kwargs):
            yield TurnStarted(1, 2)
            yield TextDelta("Hello")
            yield TurnFinished(2, "complete", "end_turn")

        service = mock.Mock(stream_reply=fake_stream_reply)
        with mock.patch("ai.views.get_chat_service", return_value=service):
            res = self.post(self.alice, {"text": "hi"})
            body = b"".join(res.streaming_content).decode()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "text/event-stream")
        self.assertEqual(res["X-Accel-Buffering"], "no")
        self.assertIn("event: start", body)
        self.assertIn('event: delta\ndata: {"text":"Hello"}', body)
        self.assertIn("event: done", body)
