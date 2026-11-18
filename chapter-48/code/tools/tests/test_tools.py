import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools import contract_diff, contract_lint, spec_lint, sync_check, trace_check
from tools.openapi_util import load

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = load(ROOT / "contracts" / "openapi.json")
CONTRACT_V1 = load(ROOT / "contracts" / "openapi.v1.json")
SPEC = (ROOT / "docs" / "specs" / "share-conversation.md").read_text(encoding="utf-8")

CREATE = "/api/v1/conversations/{conversation_id}/share/"
REVOKE = "/api/v1/conversations/{conversation_id}/share/{link_id}/"


class SpecLintTests(unittest.TestCase):
    def test_the_real_spec_is_ready(self):
        self.assertEqual(spec_lint.lint(SPEC), [])

    def test_missing_section_is_reported(self):
        broken = SPEC.replace("## Security and privacy", "## Something else")
        self.assertIn("missing section: Security and privacy", spec_lint.lint(broken))

    def test_gap_in_ids_is_reported(self):
        broken = SPEC.replace("- AC-5:", "- AC-15:")
        self.assertIn("acceptance criterion ids are not consecutive from AC-1", spec_lint.lint(broken))

    def test_duplicate_ids_are_reported(self):
        broken = SPEC.replace("- AC-6:", "- AC-5:")
        self.assertIn("duplicate acceptance criterion ids", spec_lint.lint(broken))

    def test_unresolved_open_question_blocks(self):
        broken = SPEC.replace("[resolved] No: it is a snapshot (AC-4).", "Maybe.")
        self.assertTrue(any("open question" in p for p in spec_lint.lint(broken)))

    def test_placeholders_are_reported(self):
        self.assertTrue(any("placeholder" in p for p in spec_lint.lint(SPEC + "\nTBD: pricing\n")))


class TraceCheckTests(unittest.TestCase):
    def make_tree(self, files: dict[str, str]) -> Path:
        tmp = Path(tempfile.mkdtemp())
        for name, text in files.items():
            path = tmp / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return tmp

    def test_reads_criteria(self):
        self.assertEqual(len(trace_check.acceptance_criteria(SPEC)), 13)

    def test_detects_covered_and_missing(self):
        tree = self.make_tree({
            "backend/test_a.py": "def test_ac1_x(): pass\n# AC-2\n",
            "web/x.test.tsx": 'it("AC-3: reads", () => {})\n',
            "web/not_a_test.tsx": "AC-4",
        })
        criteria, covered = trace_check.coverage(SPEC, [tree])
        self.assertTrue(covered[1] and covered[2] and covered[3])
        self.assertFalse(covered[4])

    def test_ac12_is_not_mistaken_for_ac1(self):
        tree = self.make_tree({"backend/test_b.py": "# AC-12 only\n"})
        _, covered = trace_check.coverage(SPEC, [tree])
        self.assertTrue(covered[12])
        self.assertFalse(covered[1])

    def test_node_modules_are_ignored(self):
        tree = self.make_tree({"web/node_modules/pkg/test_x.js": "AC-5"})
        _, covered = trace_check.coverage(SPEC, [tree])
        self.assertFalse(covered[5])

    def test_the_real_project_covers_every_criterion(self):
        _, covered = trace_check.coverage(SPEC, [ROOT / "backend", ROOT / "web", ROOT / "mobile"])
        missing = [n for n, files in covered.items() if not files]
        self.assertEqual(missing, [])


class ContractLintTests(unittest.TestCase):
    def test_the_real_contract_passes(self):
        self.assertEqual(contract_lint.lint(CONTRACT), [])

    def test_missing_operation_id(self):
        doc = copy.deepcopy(CONTRACT)
        del doc["paths"][CREATE]["post"]["operationId"]
        self.assertTrue(any(p.startswith("C1") for p in contract_lint.lint(doc)))

    def test_duplicate_and_ugly_operation_ids(self):
        doc = copy.deepcopy(CONTRACT)
        doc["paths"][CREATE]["get"]["operationId"] = "createShareLink"
        doc["paths"][REVOKE]["delete"]["operationId"] = "Revoke_Link"
        problems = contract_lint.lint(doc)
        self.assertTrue(any("also used by" in p for p in problems))
        self.assertTrue(any("not camelCase" in p for p in problems))

    def test_endpoint_without_security_is_flagged_but_explicit_public_is_fine(self):
        doc = copy.deepcopy(CONTRACT)
        del doc["security"]
        problems = contract_lint.lint(doc)
        self.assertTrue(any(p.startswith("C4") and "share/" in p for p in problems))
        self.assertFalse(any(p.startswith("C4") and "/public/" in p for p in problems))  # security: []

    def test_missing_error_response(self):
        doc = copy.deepcopy(CONTRACT)
        doc["paths"][REVOKE]["delete"]["responses"] = {"204": {"description": "ok"}}
        self.assertTrue(any(p.startswith("C5") for p in contract_lint.lint(doc)))

    def test_undeclared_path_parameter(self):
        doc = copy.deepcopy(CONTRACT)
        doc["paths"][REVOKE]["delete"]["parameters"] = doc["paths"][REVOKE]["delete"]["parameters"][:1]
        self.assertTrue(any(p.startswith("C6") and "link_id" in p for p in contract_lint.lint(doc)))

    def test_untyped_success_response(self):
        doc = copy.deepcopy(CONTRACT)
        doc["paths"][CREATE]["post"]["responses"]["201"]["content"]["application/json"]["schema"] = {"type": "object"}
        self.assertTrue(any(p.startswith("C7") for p in contract_lint.lint(doc)))


class ContractDiffTests(unittest.TestCase):
    def levels(self, old, new):
        return [(c.level, c.what) for c in contract_diff.diff(old, new)]

    def test_identical_contracts_have_no_changes(self):
        self.assertEqual(contract_diff.diff(CONTRACT, CONTRACT), [])

    def test_adding_view_count_is_safe(self):
        changes = contract_diff.diff(CONTRACT_V1, CONTRACT)
        self.assertEqual({c.level for c in changes}, {"SAFE"})
        self.assertEqual(len(changes), 2)

    def test_removed_endpoint_is_breaking(self):
        new = copy.deepcopy(CONTRACT)
        del new["paths"][REVOKE]
        self.assertIn(("BREAKING", "endpoint was removed"), self.levels(CONTRACT, new))

    def test_removed_response_property_is_breaking(self):
        new = copy.deepcopy(CONTRACT)
        del new["components"]["schemas"]["ShareLink"]["properties"]["state"]
        self.assertIn(("BREAKING", "response property 'state' was removed"), self.levels(CONTRACT, new))

    def test_changed_type_is_breaking(self):
        new = copy.deepcopy(CONTRACT)
        new["components"]["schemas"]["ShareLink"]["properties"]["view_count"]["type"] = "string"
        self.assertTrue(any(l == "BREAKING" and "changed type" in w for l, w in self.levels(CONTRACT, new)))

    def test_new_required_request_property_is_breaking_but_optional_is_safe(self):
        new = copy.deepcopy(CONTRACT)
        schema = new["components"]["schemas"]["ShareLinkCreate"]
        schema["properties"]["note"] = {"type": "string"}
        self.assertIn(("SAFE", "new request property 'note'"), self.levels(CONTRACT, new))
        schema["required"] = ["note"]
        self.assertIn(("BREAKING", "new REQUIRED request property 'note'"), self.levels(CONTRACT, new))

    def test_request_property_becoming_required_is_breaking(self):
        new = copy.deepcopy(CONTRACT)
        new["components"]["schemas"]["ShareLinkCreate"]["required"] = ["expires_in"]
        self.assertIn(("BREAKING", "request property 'expires_in' became required"), self.levels(CONTRACT, new))

    def test_response_enum_change_is_a_warning(self):
        new = copy.deepcopy(CONTRACT)
        new["components"]["schemas"]["ShareLink"]["properties"]["state"]["enum"].append("paused")
        self.assertTrue(any(l == "WARNING" for l, _ in self.levels(CONTRACT, new)))

    def test_request_enum_losing_a_value_is_breaking(self):
        new = copy.deepcopy(CONTRACT)
        new["components"]["schemas"]["ShareLinkCreate"]["properties"]["expires_in"]["enum"].remove("1d")
        self.assertTrue(any(l == "BREAKING" and "no longer accepts" in w for l, w in self.levels(CONTRACT, new)))

    def test_new_required_parameter_is_breaking(self):
        new = copy.deepcopy(CONTRACT)
        new["paths"][CREATE]["get"]["parameters"].append(
            {"name": "limit", "in": "query", "required": True, "schema": {"type": "integer"}})
        self.assertTrue(any("new required query parameter 'limit'" in w for _, w in self.levels(CONTRACT, new)))

    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            old, bad = Path(d, "old.json"), Path(d, "bad.json")
            old.write_text(json.dumps(CONTRACT))
            broken = copy.deepcopy(CONTRACT)
            del broken["paths"][REVOKE]
            bad.write_text(json.dumps(broken))
            self.assertEqual(contract_diff.main(["x", str(old), str(old)]), 0)
            self.assertEqual(contract_diff.main(["x", str(old), str(bad)]), 1)
            safe = Path(d, "safe.json")
            safe.write_text(json.dumps(CONTRACT_V1))
            self.assertEqual(contract_diff.main(["x", str(safe), str(old)]), 0)
            self.assertEqual(contract_diff.main(["x", str(safe), str(old), "--strict"]), 1)


class SyncCheckTests(unittest.TestCase):
    def run_on(self, source: str) -> list[str]:
        tmp = Path(tempfile.mkdtemp())
        (tmp / "a.ts").write_text(source, encoding="utf-8")
        return sync_check.check(CONTRACT, [tmp])

    def test_known_paths_pass(self):
        self.assertEqual(self.run_on('api.GET("/api/v1/conversations/{conversation_id}/share/", {})'), [])
        self.assertEqual(self.run_on("fetch(`/api/v1/conversations/${id}/share/`)"), [])
        self.assertEqual(self.run_on("fetch(`/api/v1/conversations/${id}/share/${link}`)"), [])

    def test_typo_is_caught(self):
        problems = self.run_on('api.GET("/api/v1/conversations/{conversation_id}/shares/", {})')
        self.assertEqual(len(problems), 1)
        self.assertIn("is not in the contract", problems[0])

    def test_unknown_endpoint_is_caught(self):
        self.assertEqual(len(self.run_on('fetch("/api/v1/billing/portal/")')), 1)

    def test_the_real_project_is_in_sync(self):
        self.assertEqual(sync_check.check(CONTRACT, [ROOT / "web" / "src", ROOT / "mobile" / "src"]), [])

    def test_generated_folders_are_skipped(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "generated").mkdir()
        (tmp / "generated" / "schema.ts").write_text('"/api/v1/old/"', encoding="utf-8")
        self.assertEqual(sync_check.check(CONTRACT, [tmp]), [])


if __name__ == "__main__":
    unittest.main()
