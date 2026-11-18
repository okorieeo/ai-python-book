import unittest

from .context import (build_system, cumulative_input_tokens, estimate_tokens, normalize_alternation, plan_context)
from .errors import AIContextTooLong
from .dto import ChatMessage as M


def convo(n):
    """n alternating messages starting with user, 30 characters each (14 tokens by the estimate)."""
    return [M("user" if i % 2 == 0 else "assistant", "x" * 30) for i in range(n)]


class PlanTests(unittest.TestCase):
    def test_everything_fits(self):
        plan = plan_context(system="sys", messages=convo(5), max_input_tokens=10_000)
        self.assertEqual(len(plan.messages), 5)
        self.assertEqual(plan.dropped, 0)
        self.assertFalse(plan.needs_summary)

    def test_drops_oldest_first_and_keeps_newest(self):
        msgs = convo(9)
        # system "s" costs 5; each message 14. Budget 5 + 14*4 = 61 keeps 4 messages... then fixes the start.
        plan = plan_context(system="s", messages=msgs, max_input_tokens=61)
        self.assertIs(plan.messages[-1], msgs[-1])
        self.assertEqual(plan.messages[0].role, "user")
        self.assertTrue(plan.needs_summary)
        self.assertEqual(plan.dropped, len(msgs) - len(plan.messages))

    def test_never_starts_with_an_assistant_message(self):
        msgs = convo(8)   # last is assistant; add a final user message
        msgs.append(M("user", "x" * 30))
        for budget in range(20, 200, 7):
            try:
                plan = plan_context(system="s", messages=msgs, max_input_tokens=budget)
            except AIContextTooLong:
                continue
            self.assertEqual(plan.messages[0].role, "user", budget)
            self.assertIs(plan.messages[-1], msgs[-1])

    def test_newest_message_too_big_is_an_error_not_a_silent_cut(self):
        msgs = [M("user", "x" * 3000)]
        with self.assertRaises(AIContextTooLong):
            plan_context(system="s", messages=msgs, max_input_tokens=500)

    def test_summary_is_added_to_system_and_uses_budget(self):
        plan = plan_context(system="You help.", messages=convo(3), summary="They like chess.", max_input_tokens=10_000)
        self.assertIn("They like chess.", plan.system)
        self.assertTrue(plan.system.startswith("You help."))
        self.assertEqual(build_system("a", None), "a")
        self.assertEqual(build_system("a", ""), "a")

    def test_estimate_is_pessimistic_for_english(self):
        text = "The quick brown fox jumps over the lazy dog. " * 20   # 900 chars, ~200 real tokens
        self.assertGreaterEqual(estimate_tokens(text), 900 // 4)

    def test_estimated_input_matches_parts(self):
        plan = plan_context(system="abc", messages=convo(2), max_input_tokens=10_000)
        self.assertEqual(plan.estimated_input, estimate_tokens("abc") + 2 * estimate_tokens("x" * 30))

    def test_empty_history_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            plan_context(system="s", messages=[], max_input_tokens=100)


class NormalizeTests(unittest.TestCase):
    def test_already_alternating_is_unchanged(self):
        msgs = convo(4)
        self.assertEqual(normalize_alternation(msgs), msgs)

    def test_a_question_that_never_got_an_answer_is_merged_into_the_next(self):
        out = normalize_alternation([M("user", "first"), M("user", "second"), M("assistant", "ok")])
        self.assertEqual([m.role for m in out], ["user", "assistant"])
        self.assertEqual(out[0].content, "first\n\nsecond")

    def test_empty_messages_are_dropped_before_merging(self):
        out = normalize_alternation([M("user", "a"), M("assistant", "  "), M("user", "b")])
        self.assertEqual([m.content for m in out], ["a\n\nb"])

    def test_does_not_mutate_its_input(self):
        msgs = [M("user", "a"), M("user", "b")]
        normalize_alternation(msgs)
        self.assertEqual(len(msgs), 2)


class QuadraticGrowthTests(unittest.TestCase):
    def test_total_grows_with_the_square_of_the_turns(self):
        ten = cumulative_input_tokens(10, 300)
        twenty = cumulative_input_tokens(20, 300)
        self.assertEqual(ten, 300 * 100)       # sum of (2k-1) for k=1..10 is 10^2
        self.assertEqual(twenty, 300 * 400)    # and 20^2 for twenty turns
        self.assertEqual(twenty, 4 * ten)      # double the length, quadruple the input

    def test_system_prompt_is_paid_every_turn(self):
        self.assertEqual(cumulative_input_tokens(10, 0, system_tokens=500), 5000)


if __name__ == "__main__":
    unittest.main()
