import asyncio
import json

import httpx2
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from ai.providers import AnthropicProvider, Delta, Done, FakeProvider, ProviderError
from chat.models import Conversation, Message
from testing import make_user


def sse(*events: tuple[str, dict]) -> bytes:
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()


MESSAGE_START = ("message_start", {"type": "message_start", "message": {
    "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-test", "content": [],
    "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 25, "output_tokens": 1}}})


def delta(i, text):
    return ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}})


STREAM = sse(
    MESSAGE_START,
    ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
    delta(0, "Hel"), delta(0, "lo"), delta(0, " world"),
    ("content_block_stop", {"type": "content_block_stop", "index": 0}),
    ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                       "usage": {"output_tokens": 12}}),
    ("message_stop", {"type": "message_stop"}),
)


def provider_with(handler) -> AnthropicProvider:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key="sk-test", max_retries=0,
                                      http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
    return AnthropicProvider(api_key="sk-test", model="claude-test", summary_model="claude-test-small", client=client)


class AnthropicProviderTests(SimpleTestCase):
    def test_real_sdk_parses_a_streamed_reply_into_deltas_and_usage(self):
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.read())
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=STREAM)

        async def run():
            return [e async for e in provider_with(handler).stream(
                system="Be brief.", messages=[{"role": "user", "content": "hi"}], max_tokens=50)]

        events = asyncio.run(run())
        self.assertEqual([e.text for e in events if isinstance(e, Delta)], ["Hel", "lo", " world"])
        self.assertEqual(events[-1], Done(input_tokens=25, output_tokens=12))
        self.assertEqual((seen["body"]["model"], seen["body"]["system"], seen["body"]["stream"]),
                         ("claude-test", "Be brief.", True))
        self.assertEqual(seen["body"]["messages"], [{"role": "user", "content": "hi"}])

    def test_rate_limits_and_server_errors_become_provider_errors(self):
        for status, retryable in ((429, True), (500, True), (400, False)):
            handler = lambda r, s=status: httpx2.Response(s, json={"type": "error", "error": {
                "type": "api_error", "message": "x"}})

            async def run():
                async for _ in provider_with(handler).stream(system="s", messages=[{"role": "user", "content": "h"}], max_tokens=5):
                    pass

            with self.assertRaises(ProviderError) as ctx:
                asyncio.run(run())
            if status != 429:
                self.assertEqual(ctx.exception.retryable, retryable)

    def test_complete_returns_the_text_blocks(self):
        message = {"id": "msg_2", "type": "message", "role": "assistant", "model": "claude-test",
                   "content": [{"type": "text", "text": "A summary."}], "stop_reason": "end_turn",
                   "stop_sequence": None, "usage": {"input_tokens": 5, "output_tokens": 3}}
        provider = provider_with(lambda r: httpx2.Response(200, json=message))
        self.assertEqual(asyncio.run(provider.complete(system="s", messages=[{"role": "user", "content": "h"}], max_tokens=5)),
                         "A summary.")


class FakeProviderTests(SimpleTestCase):
    def test_fake_provider_streams_words_then_usage(self):
        async def run():
            return [e async for e in FakeProvider(reply="a b c").stream(system="", messages=[{"role": "user", "content": "x"}], max_tokens=5)]
        events = asyncio.run(run())
        self.assertEqual("".join(e.text for e in events if isinstance(e, Delta)), "a b c")
        self.assertIsInstance(events[-1], Done)


class ConversationApiTests(TestCase):
    def setUp(self):
        self.ada, self.bo = make_user(), make_user("bo@example.com")
        self.conv = Conversation.objects.create(user=self.ada, title="Plans")
        Message.objects.create(conversation=self.conv, role="user", content="hello")
        Message.objects.create(conversation=self.conv, role="assistant", content="", status="error")
        self.api = APIClient()

    def test_owner_sees_conversations_and_history_without_empty_error_rows(self):
        self.api.force_authenticate(self.ada)
        self.assertEqual([c["title"] for c in self.api.get("/api/v1/conversations/").json()], ["Plans"])
        msgs = self.api.get(f"/api/v1/conversations/{self.conv.public_id}/messages/").json()
        self.assertEqual([m["content"] for m in msgs], ["hello"])

    def test_other_users_get_404_for_read_history_and_delete(self):
        self.api.force_authenticate(self.bo)
        self.assertEqual(self.api.get("/api/v1/conversations/").json(), [])
        base = f"/api/v1/conversations/{self.conv.public_id}/"
        self.assertEqual(self.api.get(base).status_code, 404)
        self.assertEqual(self.api.get(base + "messages/").json(), [])
        self.assertEqual(self.api.delete(base).status_code, 404)
        self.assertTrue(Conversation.objects.filter(pk=self.conv.pk).exists())

    def test_owner_can_delete_and_messages_go_with_it(self):
        self.api.force_authenticate(self.ada)
        self.assertEqual(self.api.delete(f"/api/v1/conversations/{self.conv.public_id}/").status_code, 204)
        self.assertEqual(Message.objects.count(), 0)

    def test_anonymous_requests_are_rejected(self):
        self.assertEqual(self.api.get("/api/v1/conversations/").status_code, 401)
