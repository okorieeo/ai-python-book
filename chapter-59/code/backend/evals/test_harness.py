"""Self-tests for the eval harness, using scripted models. They do NOT measure any real model."""
from datetime import datetime
from unittest import TestCase

from assistant.agent import ModelTurn, Usage
from assistant.test_agent import ScriptedModel, text, use
from assistant.tools import ToolContext, ToolRegistry, Risk, Tool
from core.timeutils import UTC, get_zone
from evals.cases import CASES
from evals.harness import Case, Expect, judge, run_case, run_all, stub_registry

CTX = ToolContext(user=None, now=datetime(2026, 11, 11, 9, 0, tzinfo=UTC), tz=get_zone("Africa/Lagos"))  # 10:00 Lagos


def tiny_registry():
    schema = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
    return ToolRegistry([
        Tool("look", "Look", schema, lambda c, a: {"never": "used"}),
        Tool("kill", "Kill", schema, lambda c, a: {"never": "used"}, Risk.CONFIRM, summarize=lambda c, a: "real summary"),
    ])


class JudgeTests(TestCase):
    def test_passes_when_expectations_are_met_in_order(self):
        case = Case("c", "m", (Expect("a"), Expect("b", {"x": 1})))
        self.assertEqual(judge(case, [("a", {}), ("z", {}), ("b", {"x": 1, "y": 2})]), [])

    def test_order_matters(self):
        case = Case("c", "m", (Expect("a"), Expect("b")))
        self.assertEqual(len(judge(case, [("b", {}), ("a", {})])), 1)

    def test_argument_predicates_and_exact_values(self):
        case = Case("c", "m", (Expect("a", {"t": lambda v: "rent" in v, "n": 3}),))
        self.assertEqual(judge(case, [("a", {"t": "pay rent", "n": 3})]), [])
        self.assertTrue(judge(case, [("a", {"t": "pay rent", "n": 4})]))
        self.assertTrue(judge(case, [("a", {"n": 3})]))

    def test_forbidden_tools_fail_the_case(self):
        case = Case("c", "m", (), forbid=("kill",))
        self.assertEqual(judge(case, [("kill", {})]), ["called forbidden tool kill"])


class RunCaseTests(TestCase):
    def test_stubs_replace_handlers_but_keep_schemas_and_risk(self):
        real = tiny_registry()
        stubbed = stub_registry(real, [], {})
        self.assertEqual(stubbed.specs(), real.specs())
        self.assertIs(stubbed.get("kill").risk, Risk.CONFIRM)

    def test_a_passing_and_a_failing_run(self):
        case = Case("c", "hi", (Expect("look", {"q": "x"}),), forbid=("kill",))
        good = run_case(case, model=ScriptedModel(use(("a", "look", {"q": "x"})), text("ok")), real_registry=tiny_registry(), ctx=CTX)
        self.assertTrue(good.passed)
        bad = run_case(case, model=ScriptedModel(use(("a", "kill", {"q": "x"}))), real_registry=tiny_registry(), ctx=CTX)
        self.assertFalse(bad.passed)

    def test_the_model_is_shown_the_stamped_time(self):
        model = ScriptedModel(text("hi"))
        run_case(Case("c", "hello", ()), model=model, real_registry=tiny_registry(), ctx=CTX)
        self.assertIn("[Sent 2026-11-11T10:00 Wednesday, Africa/Lagos]", model.seen[0][0]["content"])

    def test_run_all_reports_a_score(self):
        lines = []
        cases = (Case("one", "m", ()), Case("two", "m", (Expect("look"),)))
        run_all(cases, model=ScriptedModel(text("a"), text("b")), real_registry=tiny_registry(), ctx=CTX, report=lines.append)
        self.assertEqual(lines[-1], "1/2 passed")


class CatalogueTests(TestCase):
    def test_every_case_is_well_formed(self):
        names = [c.name for c in CASES]
        self.assertEqual(len(names), len(set(names)))
        for case in CASES:
            self.assertTrue(case.expect, case.name)
