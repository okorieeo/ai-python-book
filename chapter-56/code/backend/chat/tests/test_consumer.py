import asyncio
from unittest.mock import patch

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import TransactionTestCase

from accounts.views import TICKET_PREFIX
from ai.providers import FakeProvider
from billing.models import Subscription
from billing.notify import notify_plan_changed
from chat.models import Conversation, Message, UsageDay
from chat.routing import websocket_urlpatterns
from testing import ensure_plans, make_user

APP = URLRouter(websocket_urlpatterns)


def ticket_for(user) -> str:
    ticket = f"t-{user.pk}-{id(object())}"
    cache.set(TICKET_PREFIX + ticket, user.pk, timeout=60)
    return ticket


class ChatSocketTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        ensure_plans(free_limit=3, pro_limit=50)
        self.user = make_user()
        self.provider = FakeProvider(reply="Hello from the model")
        patcher = patch("chat.consumers.get_provider", lambda: self.provider)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def connect(self, user=None, ticket=None):
        user = user or self.user
        ticket = ticket if ticket is not None else await sync_to_async(ticket_for)(user)
        comm = WebsocketCommunicator(APP, f"/ws/chat/?ticket={ticket}")
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        return comm

    async def collect_until(self, comm, *types, limit=30):
        frames = []
        for _ in range(limit):
            frame = await comm.receive_json_from(timeout=3)
            frames.append(frame)
            if frame["type"] in types:
                return frames
        self.fail(f"never saw {types}; got {[f['type'] for f in frames]}")

    # ---- authentication --------------------------------------------------------------------------
    async def test_connection_without_a_valid_ticket_is_closed_with_4401(self):
        for ticket in ("", "forged-ticket"):
            comm = await self.connect(ticket=ticket)
            out = await comm.receive_output(timeout=3)
            self.assertEqual((out["type"], out["code"]), ("websocket.close", 4401))

    async def test_a_ticket_cannot_be_used_twice(self):
        ticket = await sync_to_async(ticket_for)(self.user)
        first = await self.connect(ticket=ticket)
        self.assertEqual((await first.receive_json_from())["type"], "ready")
        second = await self.connect(ticket=ticket)
        self.assertEqual((await second.receive_output())["code"], 4401)
        await first.disconnect()

    async def test_ready_frame_reports_plan_and_usage(self):
        comm = await self.connect()
        ready = await comm.receive_json_from()
        self.assertEqual(ready["plan"]["code"], "free")
        self.assertEqual(ready["usage"], {"used": 0, "limit": 3})
        await comm.disconnect()

    # ---- streaming ------------------------------------------------------------------------------------
    async def test_a_message_streams_back_and_is_saved(self):
        comm = await self.connect()
        await comm.receive_json_from()  # ready
        await comm.send_json_to({"type": "chat.send", "conversation_id": None, "content": "Hi there", "client_id": "c1"})
        frames = await self.collect_until(comm, "chat.done")
        types = [f["type"] for f in frames]
        self.assertEqual(types[0], "chat.started")
        self.assertEqual(frames[0]["client_id"], "c1")
        self.assertEqual("".join(f["text"] for f in frames if f["type"] == "chat.delta"), "Hello from the model")
        self.assertEqual(frames[-1]["status"], "complete")
        self.assertEqual(frames[-1]["remaining"], 2)
        msgs = await sync_to_async(lambda: list(Message.objects.values_list("role", "content", "status")))()
        self.assertEqual(msgs, [("user", "Hi there", "complete"), ("assistant", "Hello from the model", "complete")])
        used = await sync_to_async(lambda: UsageDay.objects.get().output_tokens)()
        self.assertGreater(used, 0)
        await comm.disconnect()

    async def test_a_second_message_sends_the_earlier_ones_as_memory(self):
        comm = await self.connect()
        await comm.receive_json_from()
        await comm.send_json_to({"type": "chat.send", "content": "My name is Ada"})
        started = (await self.collect_until(comm, "chat.done"))[0]
        await comm.send_json_to({"type": "chat.send", "conversation_id": started["conversation_id"],
                                 "content": "What is my name?"})
        await self.collect_until(comm, "chat.done")
        sent = self.provider.calls[-1]["messages"]
        self.assertEqual([m["content"] for m in sent], ["My name is Ada", "Hello from the model", "What is my name?"])
        await comm.disconnect()

    async def test_stop_keeps_the_partial_answer(self):
        self.provider.reply, self.provider.delay = "one two three four five six seven eight", 0.05
        comm = await self.connect()
        await comm.receive_json_from()
        await comm.send_json_to({"type": "chat.send", "content": "talk a lot"})
        await comm.receive_json_from()  # chat.started
        await comm.receive_json_from()  # first delta
        await comm.send_json_to({"type": "chat.stop"})
        frames = await self.collect_until(comm, "chat.done")
        self.assertEqual(frames[-1]["status"], "stopped")
        reply = await sync_to_async(lambda: Message.objects.get(role="assistant"))()
        self.assertEqual(reply.status, "stopped")
        self.assertTrue(0 < len(reply.content) < len("one two three four five six seven eight"))
        await comm.disconnect()

    async def test_closing_the_socket_mid_answer_still_saves_what_was_said(self):
        self.provider.reply, self.provider.delay = "one two three four five six seven eight", 0.05
        comm = await self.connect()
        await comm.receive_json_from()
        await comm.send_json_to({"type": "chat.send", "content": "talk a lot"})
        await comm.receive_json_from()
        await comm.receive_json_from()
        await comm.disconnect()
        reply = await sync_to_async(lambda: Message.objects.get(role="assistant"))()
        self.assertEqual(reply.status, "stopped")
        self.assertTrue(reply.content.startswith("one"))

    async def test_only_one_answer_at_a_time(self):
        self.provider.reply, self.provider.delay = "a b c d e f g h", 0.05
        comm = await self.connect()
        await comm.receive_json_from()
        await comm.send_json_to({"type": "chat.send", "content": "first"})
        await comm.receive_json_from()
        await comm.send_json_to({"type": "chat.send", "content": "second"})
        frames = await self.collect_until(comm, "chat.error")
        self.assertEqual(frames[-1]["code"], "busy")
        await comm.send_json_to({"type": "chat.stop"})
        await self.collect_until(comm, "chat.done")
        await comm.disconnect()

    # ---- limits and validation --------------------------------------------------------------------
    async def test_daily_limit_blocks_the_fourth_message_on_the_free_plan(self):
        comm = await self.connect()
        await comm.receive_json_from()
        for i in range(3):
            await comm.send_json_to({"type": "chat.send", "content": f"m{i}"})
            await self.collect_until(comm, "chat.done")
        await comm.send_json_to({"type": "chat.send", "content": "m3", "client_id": "late"})
        err = (await self.collect_until(comm, "chat.error"))[-1]
        self.assertEqual((err["code"], err["client_id"]), ("limit_reached", "late"))
        await comm.disconnect()

    async def test_other_users_conversations_are_not_found(self):
        bo = await sync_to_async(make_user)("bo@example.com")
        conv = await sync_to_async(Conversation.objects.create)(user=bo, title="private")
        comm = await self.connect()
        await comm.receive_json_from()
        await comm.send_json_to({"type": "chat.send", "conversation_id": str(conv.public_id), "content": "peek"})
        self.assertEqual((await self.collect_until(comm, "chat.error"))[-1]["code"], "not_found")
        self.assertEqual(await sync_to_async(Message.objects.count)(), 0)
        await comm.disconnect()

    async def test_bad_frames_get_errors_instead_of_crashing_the_socket(self):
        comm = await self.connect()
        await comm.receive_json_from()
        await comm.send_to(text_data="{not json")
        self.assertEqual((await comm.receive_json_from())["code"], "invalid_message")
        await comm.send_to(text_data="[1,2,3]")
        self.assertEqual((await comm.receive_json_from())["code"], "invalid_message")
        await comm.send_json_to({"type": "nope"})
        self.assertEqual((await comm.receive_json_from())["code"], "invalid_message")
        await comm.send_json_to({"type": "chat.send", "content": "x" * 501})
        self.assertEqual((await comm.receive_json_from())["code"], "too_long")
        await comm.send_json_to({"type": "ping"})
        self.assertEqual((await comm.receive_json_from())["type"], "pong")
        await comm.disconnect()

    # ---- provider failures ------------------------------------------------------------------------
    async def test_provider_failure_before_any_text_refunds_the_message(self):
        self.provider.fail_after = 0
        comm = await self.connect()
        await comm.receive_json_from()
        await comm.send_json_to({"type": "chat.send", "content": "hello"})
        err = (await self.collect_until(comm, "chat.error"))[-1]
        self.assertEqual(err["code"], "provider_error")
        used = await sync_to_async(lambda: UsageDay.objects.get().messages)()
        self.assertEqual(used, 0)
        status = await sync_to_async(lambda: Message.objects.get(role="assistant").status)()
        self.assertEqual(status, "error")
        await comm.disconnect()

    async def test_provider_failure_midway_keeps_the_partial_text_and_the_charge(self):
        self.provider.reply, self.provider.fail_after = "one two three four", 2
        comm = await self.connect()
        await comm.receive_json_from()
        await comm.send_json_to({"type": "chat.send", "content": "hello"})
        await self.collect_until(comm, "chat.error")
        reply = await sync_to_async(lambda: Message.objects.get(role="assistant"))()
        self.assertEqual((reply.status, reply.content), ("error", "one two"))
        self.assertEqual(await sync_to_async(lambda: UsageDay.objects.get().messages)(), 1)
        await comm.disconnect()

    # ---- billing pushes ---------------------------------------------------------------------------------
    async def test_plan_changes_are_pushed_to_open_sockets(self):
        comm = await self.connect()
        await comm.receive_json_from()
        _, pro = await sync_to_async(ensure_plans)()
        from django.utils import timezone
        from datetime import timedelta
        await sync_to_async(Subscription.objects.create)(
            user=self.user, plan=pro, status="active", gateway="stripe",
            current_period_end=timezone.now() + timedelta(days=30))
        await sync_to_async(notify_plan_changed)(self.user)
        push = await comm.receive_json_from(timeout=3)
        self.assertEqual(push["type"], "plan.updated")
        self.assertEqual(push["plan"]["code"], "pro")
        await comm.disconnect()

    async def test_a_pro_user_gets_the_pro_limit(self):
        from datetime import timedelta
        from django.utils import timezone
        _, pro = await sync_to_async(ensure_plans)(free_limit=1, pro_limit=2)
        await sync_to_async(Subscription.objects.create)(
            user=self.user, plan=pro, status="active", gateway="stripe",
            current_period_end=timezone.now() + timedelta(days=30))
        comm = await self.connect()
        self.assertEqual((await comm.receive_json_from())["usage"]["limit"], 2)
        await comm.disconnect()
