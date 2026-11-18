"""Tests for assistant.history and for the histories the agent loop produces. Plain unittest."""
from datetime import datetime
from unittest import TestCase

from core.timeutils import UTC, get_zone
from assistant.agent import Limits, run_agent, resolve_pending, resume_agent
from assistant.history import history_problems, is_person_message, trim_history
from assistant.test_agent import ASK, CTX, SYSTEM, Recorder, ScriptedModel, text, use


def person(t):
    return {"role": "user", "content": t}


def assistant(t):
    return {"role": "assistant", "content": [{"type": "text", "text": t}]}


def tool_turn(n):
    return [
        {"role": "assistant", "content": [{"type": "tool_use", "id": f"t{n}", "name": "lookup", "input": {"q": "x"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{n}", "content": "{}", "is_error": False}]},
    ]


class TrimTests(TestCase):
    def conversation(self, turns):
        out = []
        for n in range(turns):
            out += [person(f"q{n}")] + tool_turn(n) + [assistant(f"a{n}")]
        return out

    def test_short_histories_are_untouched(self):
        history = self.conversation(3)
        self.assertEqual(trim_history(history, keep_turns=5), history)

    def test_trims_at_a_person_message_and_keeps_pairs_together(self):
        history = self.conversation(10)
        trimmed = trim_history(history, keep_turns=3)
        self.assertEqual(trimmed[0], person("q7"))
        self.assertEqual(len(trimmed), 12)
        self.assertEqual(history_problems(trimmed), [])

    def test_tool_result_messages_are_not_person_messages(self):
        self.assertFalse(is_person_message(tool_turn(0)[1]))
        self.assertTrue(is_person_message(person("hi")))
        self.assertTrue(is_person_message({"role": "user", "content": [{"type": "text", "text": "hi"}]}))
        self.assertFalse(is_person_message(assistant("hi")))

    def test_does_not_modify_its_input(self):
        history = self.conversation(10)
        before = list(history)
        trim_history(history, keep_turns=2)
        self.assertEqual(history, before)


class HistoryProblemTests(TestCase):
    def test_detects_unanswered_tool_use(self):
        broken = [person("hi"), tool_turn(0)[0], person("again")]
        self.assertEqual(len(history_problems(broken)), 1)

    def test_detects_wrong_start(self):
        self.assertTrue(history_problems([assistant("hello")]))

    def test_valid_history(self):
        self.assertEqual(history_problems([person("hi")] + tool_turn(0) + [assistant("ok")]), [])


class AgentProducesValidHistoriesTests(TestCase):
    """Whatever stops the loop, the saved history must be usable for the person's next message."""

    def check(self, result):
        self.assertEqual(history_problems(result.messages[:-1] if result.status == "needs_confirmation" else result.messages), [])

    def test_normal_run(self):
        rec = Recorder()
        result = run_agent(ScriptedModel(use(("a", "lookup", {"q": "x"})), text("ok")), rec.registry, CTX, system=SYSTEM, messages=ASK)
        self.check(result)

    def test_step_limit_run(self):
        rec = Recorder()
        model = ScriptedModel(*[use((f"t{n}", "lookup", {"q": "x"})) for n in range(5)])
        self.check(run_agent(model, rec.registry, CTX, system=SYSTEM, messages=ASK, limits=Limits(max_steps=2)))

    def test_truncated_run(self):
        from assistant.agent import ModelTurn
        cut = ModelTurn([{"type": "tool_use", "id": "a", "name": "save", "input": {}}], "max_tokens")
        self.check(run_agent(ScriptedModel(cut), Recorder().registry, CTX, system=SYSTEM, messages=ASK))

    def test_confirmation_round_trip(self):
        rec = Recorder()
        model = ScriptedModel(use(("a", "lookup", {"q": "x"}), ("b", "erase", {"q": "y"})), text("done"))
        paused = run_agent(model, rec.registry, CTX, system=SYSTEM, messages=ASK)
        blocks = resolve_pending(rec.registry, CTX, paused.pending, {"b": False})
        done = resume_agent(model, rec.registry, CTX, system=SYSTEM, messages=paused.messages, results=paused.results + blocks)
        self.check(done)
