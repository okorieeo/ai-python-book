"""Run: python -m unittest core.chat.test_chat -v"""
import unittest

from core.chat.history import ContextTooLong, Message, estimate_tokens, trim_history
from core.chat.memory import EchoProvider, FlakyProvider, MemoryRepo, RefusingProvider
from core.chat.service import (ChatService, Invalid, NotFound, ProviderRejected, ProviderTimeout, ServiceUnavailable)


def msgs(*pairs):
    return [Message(r, c) for r, c in pairs]


class HistoryTests(unittest.TestCase):
    def test_everything_fits(self):
        m = msgs(("user", "hi"), ("assistant", "hello"), ("user", "bye"))
        kept, dropped = trim_history(m, max_tokens=100)
        self.assertEqual((kept, dropped), (m, 0))

    def test_oldest_are_dropped_first_and_order_is_kept(self):
        m = msgs(("user", "a" * 40), ("assistant", "b" * 40), ("user", "c" * 40), ("assistant", "d" * 40), ("user", "e" * 40))
        kept, dropped = trim_history(m, max_tokens=30)          # 10 tokens per message: room for three
        self.assertEqual([x.content[0] for x in kept], ["c", "d", "e"])
        self.assertEqual(dropped, 2)

    def test_never_starts_with_an_assistant_message(self):
        m = msgs(("user", "a" * 40), ("assistant", "b" * 40), ("user", "c" * 40))
        kept, dropped = trim_history(m, max_tokens=20)          # room for two: assistant+user, so the assistant is trimmed too
        self.assertEqual([x.role for x in kept], ["user"])
        self.assertEqual(dropped, 2)

    def test_last_message_always_kept_or_error(self):
        m = msgs(("user", "x" * 4000))
        with self.assertRaises(ContextTooLong):
            trim_history(m, max_tokens=500)
        kept, _ = trim_history(m, max_tokens=1000)
        self.assertEqual(len(kept), 1)

    def test_reserve_and_system_tokens_reduce_the_budget(self):
        m = msgs(("user", "a" * 40), ("user", "b" * 40))
        kept, dropped = trim_history(m, max_tokens=30, system_tokens=10, reserve_reply=10)
        self.assertEqual((len(kept), dropped), (1, 1))

    def test_last_must_be_user(self):
        with self.assertRaises(ValueError):
            trim_history(msgs(("user", "a"), ("assistant", "b")), max_tokens=100)
        with self.assertRaises(ValueError):
            trim_history([], max_tokens=100)

    def test_estimate_is_at_least_one(self):
        self.assertEqual(estimate_tokens(""), 1)
        self.assertEqual(estimate_tokens("a" * 400), 100)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryRepo()
        self.repo.create_conversation("ada", "c1")
        self.repo.create_conversation("bo", "c2")
        self.provider = EchoProvider()
        self.svc = ChatService(self.repo, self.provider)

    def send(self, text="hello", key="key-1", user="ada", conv="c1", svc=None):
        return (svc or self.svc).send(user_id=user, conversation_id=conv, text=text, idempotency_key=key)

    def test_happy_path_saves_both_messages_in_order(self):
        r = self.send()
        self.assertEqual((r.user_message.role, r.user_message.status), ("user", "ok"))
        self.assertEqual((r.assistant_message.role, r.assistant_message.content), ("assistant", "echo: hello"))
        self.assertEqual([m.role for m in self.repo.history("c1")], ["user", "assistant"])

    def test_other_users_conversation_is_not_found(self):
        with self.assertRaises(NotFound):
            self.send(user="ada", conv="c2")
        with self.assertRaises(NotFound):
            self.send(conv="does-not-exist")
        self.assertEqual(self.repo.history("c2"), [])
        self.assertEqual(self.provider.calls, [])

    def test_validation(self):
        for text in ("", "   ", None):
            with self.assertRaises(Invalid):
                self.send(text=text)
        with self.assertRaises(Invalid):
            self.send(text="x" * 8001)
        with self.assertRaises(Invalid):
            self.send(key="")
        with self.assertRaises(Invalid):
            self.send(key="k" * 81)
        self.assertEqual(self.provider.calls, [])

    def test_same_key_returns_the_same_answer_without_calling_the_provider_again(self):
        a = self.send()
        b = self.send()
        self.assertTrue(b.deduplicated)
        self.assertEqual(a.assistant_message.id, b.assistant_message.id)
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(len(self.repo.history("c1")), 2)

    def test_same_key_in_another_conversation_is_independent(self):
        self.repo.create_conversation("ada", "c3")
        self.send(conv="c1")
        r = self.send(conv="c3")
        self.assertFalse(r.deduplicated)
        self.assertEqual(len(self.provider.calls), 2)

    def test_timeout_marks_failed_and_retry_with_same_key_succeeds(self):
        flaky = FlakyProvider(fail_times=1)
        svc = ChatService(self.repo, flaky)
        with self.assertRaises(ServiceUnavailable):
            self.send(svc=svc)
        self.assertEqual(self.repo.find_by_key("c1", "key-1").status, "failed")
        r = self.send(svc=svc)
        self.assertEqual(r.assistant_message.content, "echo: hello")
        self.assertEqual(len([m for m in self.repo.history("c1") if m.role == "user"]), 1)   # no second copy of the question

    def test_user_message_is_saved_before_the_provider_is_called(self):
        seen = {}

        class Spy(EchoProvider):
            def complete(inner, messages, *, timeout):  # noqa: N805
                seen["status"] = [m.status for m in self.repo.history("c1")]
                return "ok"
        self.send(svc=ChatService(self.repo, Spy()))
        self.assertEqual(seen["status"], ["pending"])

    def test_provider_refusal_is_a_400_and_is_not_retried_as_pending(self):
        svc = ChatService(self.repo, RefusingProvider())
        with self.assertRaises(Invalid):
            self.send(svc=svc)
        self.assertEqual(self.repo.find_by_key("c1", "key-1").status, "blocked")

    def test_input_check_blocks_without_calling_the_provider(self):
        svc = ChatService(self.repo, self.provider, check_input=lambda t: "attack" not in t)
        r = self.send(text="how to attack", svc=svc)
        self.assertEqual(r.assistant_message.content, "I can't help with that request.")
        self.assertEqual(r.user_message.status, "blocked")
        self.assertEqual(self.provider.calls, [])
        again = self.send(text="how to attack", svc=svc)
        self.assertTrue(again.deduplicated)

    def test_blocked_and_failed_messages_are_not_sent_as_history(self):
        svc = ChatService(self.repo, self.provider, check_input=lambda t: "bad" not in t)
        self.send(text="bad thing", key="k1", svc=svc)
        self.send(text="good thing", key="k2", svc=svc)
        sent = self.provider.calls[-1]
        self.assertEqual([m["content"] for m in sent], ["good thing"])

    def test_history_is_trimmed_to_the_context_budget(self):
        svc = ChatService(self.repo, self.provider, max_context_tokens=60, reserve_reply_tokens=20)
        for i in range(5):
            self.send(text=f"message {i} " + "x" * 60, key=f"k{i}", svc=svc)
        self.assertLessEqual(len(self.provider.calls[-1]), 3)
        self.assertTrue(self.provider.calls[-1][-1]["content"].startswith("message 4"))

    def test_prepare_hook_redacts_and_restores(self):
        def prepare(messages):
            redacted = [{**m, "content": m["content"].replace("ada@example.com", "[EMAIL_1]")} for m in messages]
            return redacted, lambda t: t.replace("[EMAIL_1]", "ada@example.com")
        svc = ChatService(self.repo, self.provider, prepare=prepare)
        r = self.send(text="mail ada@example.com", svc=svc)
        self.assertNotIn("ada@example.com", self.provider.calls[0][-1]["content"])
        self.assertIn("ada@example.com", r.assistant_message.content)

    def test_stuck_pending_message_is_not_duplicated(self):
        m = self.repo.add("c1", "user", "hello", status="pending", key="key-1")
        with self.assertRaises(ServiceUnavailable):
            self.send()
        self.assertEqual(len(self.repo.history("c1")), 1)
        self.assertEqual(m.status, "pending")


if __name__ == "__main__":
    unittest.main()
