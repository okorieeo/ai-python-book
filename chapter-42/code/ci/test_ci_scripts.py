import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import changed_areas
import gate

HERE = Path(__file__).parent
ALL_FALSE = dict.fromkeys(changed_areas.AREAS, False)
ALL_TRUE = dict.fromkeys(changed_areas.AREAS, True)


def run_script(
    name: str, *args: str, stdin: bytes = b"", env: dict | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HERE / name), *args], input=stdin, capture_output=True, env=env, check=False
    )


class ChangedAreasTests(unittest.TestCase):
    def test_a_backend_only_change_runs_only_the_backend(self):
        result = changed_areas.classify(["backend/chat/views.py", "backend/pyproject.toml"])
        self.assertEqual(result, {"backend": True, "web": False, "mobile": False})

    def test_each_area_is_detected_by_its_folder(self):
        result = changed_areas.classify(["web/app/page.tsx", "mobile/hooks/useDictation.ts"])
        self.assertEqual(result, {"backend": False, "web": True, "mobile": True})

    def test_a_change_to_the_pipeline_or_shared_files_runs_everything(self):
        for path in (".github/workflows/ci.yml", "ci/gate.py", ".pre-commit-config.yaml"):
            self.assertEqual(changed_areas.classify([path, "docs/readme.md"]), ALL_TRUE, path)

    def test_documentation_only_runs_nothing(self):
        self.assertEqual(changed_areas.classify(["README.md", "docs/guide.md"]), ALL_FALSE)

    def test_look_alike_folders_do_not_count(self):
        self.assertEqual(
            changed_areas.classify(["backend-notes/a.md", "webinar/b.md", "mobile_old/c.md"]), ALL_FALSE
        )

    def test_windows_paths_and_dot_slash_are_understood(self):
        self.assertTrue(changed_areas.classify(["backend\\chat\\x.py"])["backend"])
        self.assertTrue(changed_areas.classify(["./web/a.ts"])["web"])

    def test_nul_separated_input_keeps_odd_file_names_whole(self):
        data = b"backend/a b.py\0web/\xc3\xa9.ts\0"
        self.assertEqual(changed_areas.parse_nul_separated(data), ["backend/a b.py", "web/\u00e9.ts"])

    def test_the_command_line_output_and_the_all_flag(self):
        self.assertEqual(
            run_script("changed_areas.py", stdin=b"mobile/a.ts\0").stdout.decode(),
            "backend=false\nweb=false\nmobile=true\n",
        )
        self.assertEqual(
            run_script("changed_areas.py", "--all").stdout.decode(), "backend=true\nweb=true\nmobile=true\n"
        )


class GateTests(unittest.TestCase):
    @staticmethod
    def needs(**results):
        return {name: {"result": result} for name, result in results.items()}

    def test_success_and_skipped_pass(self):
        ok, _ = gate.evaluate(
            self.needs(changes="success", backend="success", web="skipped", mobile="skipped")
        )
        self.assertTrue(ok)

    def test_a_failed_or_cancelled_job_fails_the_gate(self):
        for bad in ("failure", "cancelled"):
            ok, problems = gate.evaluate(self.needs(changes="success", backend=bad, web="skipped"))
            self.assertFalse(ok)
            self.assertIn(f"backend: {bad}", problems)

    def test_if_change_detection_itself_failed_nothing_can_be_trusted(self):
        ok, _ = gate.evaluate(
            self.needs(changes="failure", backend="skipped", web="skipped", mobile="skipped")
        )
        self.assertFalse(ok)  # everything looks "skipped", which must NOT read as success

    def test_a_missing_changes_job_fails(self):
        ok, problems = gate.evaluate(self.needs(backend="success"))
        self.assertFalse(ok)
        self.assertIn("the 'changes' job is missing from needs", problems)

    def test_the_command_line_uses_the_exit_code(self):
        failing = {
            **os.environ,
            "NEEDS_JSON": '{"changes":{"result":"success"},"backend":{"result":"failure"}}',
        }
        result = run_script("gate.py", env=failing)
        self.assertEqual(result.returncode, 1)
        self.assertIn("backend: failure", result.stderr.decode())
        passing = {
            **os.environ,
            "NEEDS_JSON": '{"changes":{"result":"success"},"backend":{"result":"skipped"}}',
        }
        self.assertEqual(run_script("gate.py", env=passing).returncode, 0)


if __name__ == "__main__":
    unittest.main()
