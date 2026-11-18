"""Integration tests for the WebSocket consumer (needs Django and Channels installed)."""
from unittest import mock

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase, override_settings

from . import services
from .ai_fake import FakeProvider
from .consumers import ChatConsumer
from .models import Message, UsageRecord

User = get_user_model()
IN_MEMORY_LAYER = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

async def receive_until(communicator, wanted_type, limit=20):
    """Collect JSON messages until one with the wanted type arrives."""
    received = []
    for _ in range(limit):
        message = await communicator.receive_json_from(timeout=3)
        received.append(message)
        if message["type"] == wanted_type:
            return received
    raise AssertionError(f"never received {wanted_type}; got {[m['type'] for m in received]}")

@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER, AI_PROVIDER="fake")
class ChatConsumerTests(TransactionTestCase):
    """TransactionTestCase, because the consumer talks to the database from other threads."""

    async def connect_as(self, user):
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/")
        communicator.scope["user"] = user                # normally set by the authentication middleware
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        return communicator

    async def make_user_and_conversation(self, email="ada@example.com"):
        user = await database_sync_to_async(User.objects.create_user)(email=email, password="a-long-test-password")
        conversation = await database_sync_to_async(services.create_conversation)(user=user, title="T")
        return user, conversation

    async def test_anonymous_users_are_closed_with_4401(self):
        communicator = await self.connect_as(AnonymousUser())
        output = await communicator.receive_output(timeout=3)
        self.assertEqual((output["type"], output["code"]), ("websocket.close", 4401))

    async def test_ping_gets_pong(self):
        user, _ = await self.make_user_and_conversation()
        communicator = await self.connect_as(user)
        await communicator.send_json_to({"type": "ping", "id": "p-1"})
        self.assertEqual(await communicator.receive_json_from(timeout=3), {"type": "pong", "data": {}, "ref": "p-1"})
        await communicator.disconnect()

    async def test_invalid_json_returns_an_error_message(self):
        user, _ = await self.make_user_and_conversation()
        communicator = await self.connect_as(user)
        await communicator.send_to(text_data="{broken")
        reply = await communicator.receive_json_from(timeout=3)
        self.assertEqual((reply["type"], reply["data"]["code"]), ("error", "invalid_json"))
        await communicator.disconnect()

    async def test_message_streams_and_is_saved_and_billed(self):
        user, conversation = await self.make_user_and_conversation()
        with mock.patch("chat.consumers.get_provider", return_value=FakeProvider(delay=0, reply="hello big world")):
            communicator = await self.connect_as(user)
            await communicator.send_json_to({"type": "message.send", "id": "c-1", "data": {
                "conversation_id": str(conversation.public_id), "content": "Hi there"}})
            received = await receive_until(communicator, "assistant.end")
            await communicator.disconnect()

        types = [m["type"] for m in received]
        self.assertEqual(types[0], "message.accepted")
        self.assertEqual(received[0]["ref"], "c-1")
        self.assertEqual(types.count("assistant.delta"), 3)
        self.assertEqual(received[-1]["data"]["status"], "completed")
        self.assertEqual(await database_sync_to_async(Message.objects.count)(), 2)          # user + assistant
        self.assertEqual(await database_sync_to_async(UsageRecord.objects.filter(user=user).count)(), 1)

    async def test_other_users_conversation_is_not_found(self):
        _, conversation = await self.make_user_and_conversation("ada@example.com")
        intruder, _ = await self.make_user_and_conversation("bo@example.com")
        communicator = await self.connect_as(intruder)
        await communicator.send_json_to({"type": "message.send", "data": {
            "conversation_id": str(conversation.public_id), "content": "let me in"}})
        reply = await communicator.receive_json_from(timeout=3)
        self.assertEqual((reply["type"], reply["data"]["code"]), ("error", "not_found"))
        await communicator.disconnect()

    @override_settings(FREE_MONTHLY_TOKEN_LIMIT=10)
    async def test_quota_exceeded(self):
        user, conversation = await self.make_user_and_conversation()
        await database_sync_to_async(UsageRecord.objects.create)(user=user, input_tokens=20, output_tokens=0)
        communicator = await self.connect_as(user)
        await communicator.send_json_to({"type": "message.send", "data": {
            "conversation_id": str(conversation.public_id), "content": "hello"}})
        reply = await communicator.receive_json_from(timeout=3)
        self.assertEqual(reply["data"]["code"], "quota_exceeded")
        await communicator.disconnect()

    async def test_notifications_reach_the_users_group(self):
        from channels.layers import get_channel_layer
        user, _ = await self.make_user_and_conversation()
        communicator = await self.connect_as(user)
        await get_channel_layer().group_send(
            f"user_{user.pk}", {"type": "notify", "data": {"kind": "payment", "title": "Payment received", "body": ""}})
        reply = await communicator.receive_json_from(timeout=3)
        self.assertEqual((reply["type"], reply["data"]["title"]), ("notification", "Payment received"))
        await communicator.disconnect()
