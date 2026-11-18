import asyncio
import unittest

from .errors import (AIBudgetExceeded, AIInputError, AIOverloaded, AIBusy)
from .pricing import DEFAULT_PRICES
from .resilience import ConcurrencyLimiter
from .service import (AISettings, ChatService, ConversationNotFound, History, Turn)
from .testing import FakeLLM, Script
from .dto import (ChatMessage as M, TextDelta, TurnFailed, TurnFinished, TurnStarted, Usage)

P, F = "claude-sonnet-5-5", "claude-haiku-5-5"
OWNER = 1


class MemoryStore:
    def __init__(self, history=(), summary=None):
        self.rows = {}                 # assistant_message_id -> TurnResult or None while streaming
        self.users = []
        self.history = History(tuple(history), summary)
        self.summary_requests = 0
        self._next = 1

    async def get_history(self, *, user_id, conversation_id):
        if user_id != OWNER:
            raise ConversationNotFound()
        return self.history

    async def begin_turn(self, *, user_id, conversation_id, user_text):
        self.users.append(user_text)
        turn = Turn(self._next, self._next + 1)
        self._next += 2
        self.rows[turn.assistant_message_id] = None
        return turn

    async def finish_turn(self, *, user_id, conversation_id, turn, result):
        self.rows[turn.assistant_message_id] = result

    async def schedule_summary(self, *, user_id, conversation_id):
        self.summary_requests += 1

    @property
    def last(self):
        return list(self.rows.values())[-1]


async def allow_all(user_id, tokens):
    return None


def make(llm, store=None, *, budget=allow_all, prices="default", **cfg):
    store = store or MemoryStore()
    settings = AISettings(primary_model=P, fallback_model=F, system_prompt="You are helpful.", prompt_version="v3",
                          prices=DEFAULT_PRICES if prices == "default" else prices, **cfg)
    return ChatService(client=llm, store=store, budget_check=budget, settings=settings), store


async def run(service, text="Hi there", user_id=OWNER):
    return [e async for e in service.stream_reply(user_id=user_id, conversation_id=7, text=text)]


class HappyPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_events_text_and_ledger(self):
        llm = FakeLLM({P: [Script(chunks=["Hello", " world"], usage=Usage(100, 10))], F: [Script()]})
        service, store = make(llm)
        events = await run(service)
        self.assertIsInstance(events[0], TurnStarted)
        self.assertEqual([e.text for e in events if isinstance(e, TextDelta)], ["Hello", " world"])
        self.assertIsInstance(events[-1], TurnFinished)
        row = store.last
        self.assertEqual((row.status, row.text, row.model, row.prompt_version), ("complete", "Hello world", P, "v3"))
        self.assertEqual(row.cost_micro_usd, 100 * 2 + 10 * 10)         # $2 in, $10 out per MTok
        self.assertFalse(row.usage_estimated)
        self.assertEqual(row.request_id, "req_fake")

    async def test_model_sees_history_summary_and_the_new_message(self):
        hist = [M("user", "earlier question"), M("assistant", "earlier answer")]
        llm = FakeLLM({P: [Script()], F: [Script()]})
        service, _ = make(llm, MemoryStore(hist, summary="Likes chess."))
        await run(service, "new question")
        sent = llm.calls[0]
        self.assertEqual([m.content for m in sent.messages], ["earlier question", "earlier answer", "new question"])
        self.assertIn("Likes chess.", sent.system)
        self.assertEqual(sent.model, P)

    async def test_an_unanswered_earlier_question_is_merged_not_sent_as_two_user_turns(self):
        hist = [M("user", "unanswered question")]
        llm = FakeLLM({P: [Script()], F: [Script()]})
        service, _ = make(llm, MemoryStore(hist))
        await run(service, "follow-up")
        sent = llm.calls[0].messages
        self.assertEqual([m.role for m in sent], ["user"])
        self.assertIn("unanswered question", sent[0].content)
        self.assertIn("follow-up", sent[0].content)

    async def test_user_text_is_trimmed_before_saving_and_sending(self):
        llm = FakeLLM({P: [Script()], F: [Script()]})
        service, store = make(llm)
        await run(service, "  padded  \n")
        self.assertEqual(store.users, ["padded"])


class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_budget_exceeded_stops_everything_before_any_spend_or_save(self):
        async def broke(user_id, tokens):
            raise AIBudgetExceeded(retry_after=3600)
        llm = FakeLLM({P: [Script()], F: [Script()]})
        service, store = make(llm, budget=broke)
        with self.assertRaises(AIBudgetExceeded):
            await run(service)
        self.assertEqual(llm.calls, [])
        self.assertEqual((store.rows, store.users), ({}, []))

    async def test_budget_receives_the_estimated_cost_of_this_turn(self):
        seen = []
        async def spy(user_id, tokens):
            seen.append((user_id, tokens))
        llm = FakeLLM({P: [Script()], F: [Script()]})
        service, _ = make(llm, budget=spy, expected_output_tokens=500)
        await run(service, "x" * 300)
        self.assertEqual(seen[0][0], OWNER)
        self.assertGreater(seen[0][1], 500 + 100)

    async def test_someone_elses_conversation_is_not_found_and_nothing_is_called(self):
        llm = FakeLLM({P: [Script()], F: [Script()]})
        service, store = make(llm)
        with self.assertRaises(ConversationNotFound):
            await run(service, user_id=999)
        self.assertEqual((llm.calls, store.rows), ([], {}))

    async def test_empty_and_oversized_input_rejected(self):
        service, _ = make(FakeLLM({P: [Script()], F: [Script()]}), max_user_chars=50)
        for bad in ["", "   \n", "x" * 51]:
            with self.assertRaises(AIInputError):
                await run(service, bad)

    async def test_trimmed_history_asks_for_a_summary(self):
        hist = [M("user" if i % 2 == 0 else "assistant", "y" * 300) for i in range(40)]
        service, store = make(FakeLLM({P: [Script()], F: [Script()]}), MemoryStore(hist), max_input_tokens=1500)
        await run(service)
        self.assertEqual(store.summary_requests, 1)


class FailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_model_is_recorded_and_priced_as_itself(self):
        llm = FakeLLM({P: [Script(fail_before=AIOverloaded())], F: [Script(chunks=["ok"], usage=Usage(1000, 100))]})
        service, store = make(llm)
        await run(service)
        row = store.last
        self.assertEqual(row.model, F)
        self.assertEqual(row.cost_micro_usd, 100 + 50)       # 1000 in at $0.10, 100 out at $0.50, per MTok
        self.assertEqual(row.status, "complete")

    async def test_failure_after_text_keeps_the_partial_reply(self):
        llm = FakeLLM({P: [Script(chunks=["Par", "tial"], fail_after=AIOverloaded(retry_after=4))], F: [Script()]})
        service, store = make(llm)
        events = await run(service)
        row = store.last
        self.assertEqual((row.status, row.text, row.usage_estimated, row.error_code), ("interrupted", "Partial", True, "provider_overloaded"))
        self.assertGreater(row.usage.output_tokens, 0)
        err = events[-1]
        self.assertIsInstance(err, TurnFailed)
        self.assertTrue(err.partial)
        self.assertEqual(err.retry_after, 4)
        self.assertEqual(llm.models_called(), [P])             # no silent swap to the fallback mid-answer

    async def test_total_failure_before_any_text(self):
        llm = FakeLLM({P: [Script(fail_before=AIOverloaded())], F: [Script(fail_before=AIOverloaded())]})
        service, store = make(llm)
        events = await run(service)
        row = store.last
        self.assertEqual((row.status, row.text, row.error_code), ("failed", "", "unavailable"))
        self.assertEqual(row.usage, Usage())
        self.assertFalse(events[-1].partial)
        self.assertIn("temporarily unavailable", events[-1].user_message)

    async def test_busy_server_is_a_clean_failure_not_a_crash(self):
        limiter = ConcurrencyLimiter(1, wait=0.02)
        llm = FakeLLM({P: [Script()], F: [Script()]})
        service, store = make(llm)
        service.limiter = limiter
        async with limiter.slot():
            events = await run(service)
        self.assertEqual(events[-1].code, "busy")
        self.assertEqual(llm.calls, [])
        self.assertEqual(store.last.status, "failed")

    async def test_unexpected_bug_is_logged_and_shown_as_a_generic_error(self):
        class Boom(FakeLLM):
            async def stream(self, request):
                raise RuntimeError("secret internals: db password")
                yield  # pragma: no cover
        service, store = make(Boom({P: [Script()], F: [Script()]}))
        with self.assertLogs("ai.service", level="ERROR"):
            events = await run(service)
        self.assertEqual(events[-1].code, "internal")
        self.assertNotIn("secret", events[-1].user_message)
        self.assertEqual(store.last.status, "failed")

    async def test_closing_the_stream_early_saves_what_was_seen(self):
        llm = FakeLLM({P: [Script(chunks=["One ", "two ", "three"], chunk_delay=0.01)], F: [Script()]})
        service, store = make(llm)
        gen = service.stream_reply(user_id=OWNER, conversation_id=7, text="Hi")
        await gen.__anext__()                    # TurnStarted
        first = await gen.__anext__()            # first TextDelta
        self.assertEqual(first, TextDelta("One "))
        await gen.aclose()                       # the client went away
        row = store.last
        self.assertEqual((row.status, row.text, row.usage_estimated), ("cancelled", "One ", True))

    async def test_cancelling_the_task_saves_what_was_seen(self):
        llm = FakeLLM({P: [Script(chunks=["a"] * 50, chunk_delay=0.02)], F: [Script()]})
        service, store = make(llm)
        seen = []

        async def consume():
            async for ev in service.stream_reply(user_id=OWNER, conversation_id=7, text="Hi"):
                seen.append(ev)

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        row = store.last
        self.assertEqual(row.status, "cancelled")
        self.assertTrue(0 < len(row.text) < 50)


class StopReasonTests(unittest.IsolatedAsyncioTestCase):
    async def test_max_tokens_is_marked_truncated(self):
        llm = FakeLLM({P: [Script(stop_reason="max_tokens")], F: [Script()]})
        service, store = make(llm)
        events = await run(service)
        self.assertEqual((store.last.status, events[-1].status), ("truncated", "truncated"))

    async def test_context_window_exceeded_is_also_truncated(self):
        llm = FakeLLM({P: [Script(stop_reason="model_context_window_exceeded")], F: [Script()]})
        service, store = make(llm)
        await run(service)
        self.assertEqual(store.last.status, "truncated")

    async def test_refusal_is_recorded_as_refused_not_as_an_error(self):
        llm = FakeLLM({P: [Script(chunks=[], stop_reason="refusal")], F: [Script()]})
        service, store = make(llm)
        events = await run(service)
        self.assertEqual((store.last.status, events[-1].status), ("refused", "refused"))
        self.assertIsInstance(events[-1], TurnFinished)


class UnknownPriceTests(unittest.IsolatedAsyncioTestCase):
    async def test_unpriced_model_records_unknown_cost_and_still_answers(self):
        llm = FakeLLM({P: [Script()], F: [Script()]})
        service, store = make(llm, prices={})
        events = await run(service)
        self.assertIsInstance(events[-1], TurnFinished)
        self.assertIsNone(store.last.cost_micro_usd)


if __name__ == "__main__":
    unittest.main()
