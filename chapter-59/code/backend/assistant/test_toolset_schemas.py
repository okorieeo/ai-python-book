"""Checks the tool catalogue itself: schemas are well-formed, and the arguments our eval cases expect are valid.

Needs no database: it only reads the definitions.
"""
import re
from unittest import TestCase

from assistant.toolset import build_registry
from assistant.tools import ArgumentError, Risk, validate_arguments, _TYPES
from evals.cases import CASES


class CatalogueSchemaTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = build_registry()

    def test_every_schema_is_well_formed(self):
        for tool in self.registry.tools():
            schema = tool.input_schema
            self.assertEqual(schema["type"], "object", tool.name)
            self.assertTrue(set(schema["required"]) <= set(schema["properties"]), tool.name)
            self.assertGreater(len(tool.description), 30, tool.name)  # the description is the model's only manual
            for name, spec in schema["properties"].items():
                self.assertIn(spec["type"], _TYPES, f"{tool.name}.{name}")
                if "pattern" in spec:
                    re.compile(spec["pattern"])
                if "default" in spec:
                    validate_arguments({"type": "object", "properties": {name: spec}}, {name: spec["default"]})

    def test_confirm_tools_say_what_they_do_and_are_only_deletes(self):
        confirm = {t.name for t in self.registry.tools() if t.risk is Risk.CONFIRM}
        self.assertEqual(confirm, {"delete_task", "delete_event"})

    def test_no_tool_accepts_a_user_or_owner_argument(self):
        for tool in self.registry.tools():
            for forbidden in ("user", "user_id", "owner", "owner_id", "email"):
                self.assertNotIn(forbidden, tool.input_schema["properties"], tool.name)

    def test_arguments_expected_by_the_eval_cases_pass_the_real_schemas(self):
        checked = 0
        for case in CASES:
            for want in case.expect:
                tool = self.registry.get(want.tool)
                self.assertIsNotNone(tool, f"{case.name}: no tool {want.tool}")
                exact = {k: v for k, v in want.args.items() if not callable(v)}
                try:
                    validate_arguments({**tool.input_schema, "required": []}, exact)
                except ArgumentError as exc:
                    self.fail(f"{case.name}: {exc}")
                checked += 1
        self.assertGreater(checked, 8)

    def test_tool_names_in_cases_exist(self):
        names = set(self.registry.names())
        for case in CASES:
            self.assertTrue(set(case.forbid) <= names, case.name)
            self.assertTrue(set(case.canned) <= names, case.name)
