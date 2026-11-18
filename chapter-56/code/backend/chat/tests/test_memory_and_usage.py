from datetime import date, timedelta

from django.test import TestCase

from ai.memory import build_context, estimate_tokens, needs_summary
from chat import services, usage
from chat.models import Conversation, Message
from chat.tasks import summarize_conversation
from testing import ensure_plans, make_user


def add(conv, role, text, status="complete"):
    return Message.objects.create(conversation=conv, role=role, content=text, status=status)


class ContextTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.conv = Conversation.objects.create(user=self.user)

    def test_all_messages_fit_in_order(self):
        add(self.conv, "user", "hi")
        add(self.conv, "assistant", "hello")
        add(self.conv, "user", "how are you")
        ctx = build_context(self.conv)
        self.assertEqual([m["role"] for m in ctx.messages], ["user", "assistant", "user"])
        self.assertEqual(ctx.trimmed, 0)

    def test_oldest_messages_are_trimmed_first_and_context_starts_with_user(self):
        for i in range(12):
            add(self.conv, "user", f"question {i} " + "x" * 200)
            add(self.conv, "assistant", f"answer {i} " + "y" * 200)
        ctx = build_context(self.conv, budget=300)
        self.assertGreater(ctx.trimmed, 0)
        self.assertEqual(ctx.messages[0]["role"], "user")
        self.assertIn("answer 11", ctx.messages[-1]["content"])  # the newest message always survives
        total = sum(estimate_tokens(m["content"]) for m in ctx.messages)
        self.assertLessEqual(total, 300)

    def test_newest_message_is_kept_even_if_it_alone_exceeds_the_budget(self):
        add(self.conv, "user", "z" * 4000)
        ctx = build_context(self.conv, budget=50)
        self.assertEqual(len(ctx.messages), 1)

    def test_errors_and_empty_streaming_rows_are_excluded_but_partial_replies_are_kept(self):
        add(self.conv, "user", "q")
        add(self.conv, "assistant", "partial answer", status="stopped")
        add(self.conv, "assistant", "", status="error")
        add(self.conv, "assistant", "", status="streaming")
        add(self.conv, "user", "q2")
        ctx = build_context(self.conv)
        self.assertEqual([m["content"] for m in ctx.messages], ["q", "partial answer", "q2"])

    def test_summary_replaces_old_messages_in_the_prompt(self):
        old = add(self.conv, "user", "my name is Ada")
        add(self.conv, "assistant", "nice to meet you")
        self.conv.summary, self.conv.summary_through = "User is called Ada.", old.id + 1
        self.conv.save()
        add(self.conv, "user", "what is my name?")
        ctx = build_context(self.conv)
        self.assertIn("User is called Ada.", ctx.system)
        self.assertEqual([m["content"] for m in ctx.messages], ["what is my name?"])


class SummaryTaskTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.conv = Conversation.objects.create(user=self.user)

    def fill(self, n=8):
        ids = []
        for i in range(n):
            ids.append(add(self.conv, "user", f"q{i} " + "x" * 160).id)
            ids.append(add(self.conv, "assistant", f"a{i} " + "y" * 160).id)
        return ids

    def test_short_conversations_are_not_summarised(self):
        add(self.conv, "user", "hi")
        self.assertFalse(needs_summary(self.conv))
        self.assertEqual(summarize_conversation.delay(self.conv.pk).get(), "skipped")

    def test_long_conversations_fold_old_messages_and_keep_recent_ones(self):
        ids = self.fill()
        self.assertTrue(needs_summary(self.conv))
        self.assertEqual(summarize_conversation.delay(self.conv.pk).get(), "summarized")
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.summary, "SUMMARY")
        self.assertEqual(self.conv.summary_through, ids[-3])  # the last 2 messages stay out of the summary

    def test_running_twice_does_not_summarise_the_same_messages_again(self):
        self.fill()
        summarize_conversation.delay(self.conv.pk).get()
        self.assertEqual(summarize_conversation.delay(self.conv.pk).get(), "skipped")

    def test_a_stale_worker_cannot_overwrite_a_newer_summary(self):
        self.fill()
        Conversation.objects.filter(pk=self.conv.pk).update(summary_through=1)
        stale = Conversation.objects.get(pk=self.conv.pk)
        Conversation.objects.filter(pk=self.conv.pk).update(summary_through=5, summary="newer")
        updated = Conversation.objects.filter(pk=stale.pk, summary_through=stale.summary_through).update(
            summary="stale")
        self.assertEqual(updated, 0)
        self.assertEqual(Conversation.objects.get(pk=self.conv.pk).summary, "newer")


class UsageTests(TestCase):
    def setUp(self):
        ensure_plans()
        self.user = make_user()

    def test_limit_is_enforced_exactly(self):
        results = [usage.try_consume_message(self.user, 3).allowed for _ in range(5)]
        self.assertEqual(results, [True, True, True, False, False])
        self.assertEqual(usage.get_quota(self.user, 3).used, 3)

    def test_refund_gives_a_message_back_but_never_goes_negative(self):
        usage.try_consume_message(self.user, 3)
        usage.refund_message(self.user)
        usage.refund_message(self.user)
        self.assertEqual(usage.get_quota(self.user, 3).used, 0)

    def test_each_day_and_each_user_has_its_own_counter(self):
        yesterday = date.today() - timedelta(days=1)
        usage.try_consume_message(self.user, 1, today=yesterday)
        self.assertTrue(usage.try_consume_message(self.user, 1).allowed)
        other = make_user("bo@example.com")
        self.assertTrue(usage.try_consume_message(other, 1).allowed)

    def test_refused_message_leaves_no_trace_in_the_database(self):
        for _ in range(3):
            services.start_turn(user=self.user, conversation_public_id=None, content="hello", daily_limit=3)
        before = Conversation.objects.count(), Message.objects.count()
        with self.assertRaises(services.ChatError) as ctx:
            services.start_turn(user=self.user, conversation_public_id=None, content="one more", daily_limit=3)
        self.assertEqual(ctx.exception.code, "limit_reached")
        self.assertEqual((Conversation.objects.count(), Message.objects.count()), before)


class ServiceValidationTests(TestCase):
    def setUp(self):
        self.ada, self.bo = make_user(), make_user("bo@example.com")

    def test_empty_and_too_long_messages_are_rejected(self):
        for text, code in (("   ", "invalid_message"), (None, "invalid_message"), ("x" * 501, "too_long")):
            with self.assertRaises(services.ChatError) as ctx:
                services.start_turn(user=self.ada, conversation_public_id=None, content=text, daily_limit=5)
            self.assertEqual(ctx.exception.code, code)

    def test_another_users_conversation_looks_like_it_does_not_exist(self):
        turn = services.start_turn(user=self.ada, conversation_public_id=None, content="secret", daily_limit=5)
        for cid in (str(turn.conversation.public_id), "not-a-uuid"):
            with self.assertRaises(services.ChatError) as ctx:
                services.start_turn(user=self.bo, conversation_public_id=cid, content="peek", daily_limit=5)
            self.assertEqual(ctx.exception.code, "not_found")
