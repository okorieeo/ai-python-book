import os
import tempfile
import unittest

from hookutil import decision_of, run_hook

import protect_files


class Cases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "backend/chat/migrations"))
        with open(os.path.join(self.root, "backend/chat/migrations/0001_initial.py"), "w") as fh:
            fh.write("# applied\n")

    def tearDown(self):
        self.tmp.cleanup()

    def ev(self, path):
        return protect_files.evaluate(path, self.root)[0]

    def test_secrets_and_keys_are_denied(self):
        for p in [".env", ".env.local", ".env.production", "backend/.env", "mobile/AuthKey_ABC123.p8", "certs/server.pem", "keys/private.key",
                  "id_rsa", "secrets/token.txt", "config/service-account-prod.json", "gcp-credentials.json", ".ENV", "app.keystore"]:
            with self.subTest(path=p):
                self.assertEqual(self.ev(p), "deny", p)

    def test_example_files_are_fine(self):
        for p in [".env.example", "backend/.env.sample", ".env.template"]:
            self.assertIsNone(self.ev(p), p)

    def test_git_internals_are_denied(self):
        self.assertEqual(self.ev(".git/config"), "deny")
        self.assertEqual(self.ev("sub/.git/hooks/pre-commit"), "deny")

    def test_lockfiles_are_denied(self):
        for p in ["web/package-lock.json", "yarn.lock", "backend/poetry.lock", "uv.lock", "pnpm-lock.yaml"]:
            self.assertEqual(self.ev(p), "deny", p)

    def test_an_existing_migration_is_history_but_a_new_one_is_welcome(self):
        self.assertEqual(self.ev("backend/chat/migrations/0001_initial.py"), "deny")
        self.assertIsNone(self.ev("backend/chat/migrations/0002_add_title.py"))
        self.assertIsNone(self.ev("backend/chat/migrations/__init__.py"))

    def test_the_guardrails_themselves_ask(self):
        for p in [".claude/hooks/guard_bash.py", ".claude/settings.json", ".claude/settings.local.json"]:
            self.assertEqual(self.ev(p), "ask", p)

    def test_ordinary_source_files_are_fine(self):
        for p in ["backend/chat/views.py", "web/app/page.tsx", "README.md", "mobile/app.config.ts"]:
            self.assertIsNone(self.ev(p), p)

    def test_path_tricks_do_not_slip_through(self):
        self.assertEqual(self.ev("backend/../.env"), "deny")
        self.assertEqual(self.ev("./backend/./chat/../chat/migrations/0001_initial.py"), "deny")
        self.assertEqual(self.ev(os.path.join(self.root, ".env")), "deny")
        self.assertEqual(self.ev("backend\\.env"), "deny")                 # a Windows-style separator

    def test_a_path_outside_the_project_asks(self):
        self.assertEqual(self.ev("/etc/hosts"), "ask")
        self.assertEqual(self.ev("../../outside.txt"), "ask")
        self.assertEqual(self.ev(os.path.dirname(self.root) + "/other/x.py"), "ask")

    def test_a_sibling_folder_with_the_same_prefix_is_outside(self):
        self.assertEqual(self.ev(self.root + "-evil/file.py"), "ask")

    def test_empty_path_is_ignored(self):
        self.assertIsNone(self.ev(""))


class Protocol(unittest.TestCase):
    def test_edit_of_env_is_denied_over_the_real_protocol(self):
        with tempfile.TemporaryDirectory() as d:
            payload = {"tool_name": "Edit", "tool_input": {"file_path": os.path.join(d, ".env")}}
            code, out, _ = run_hook("protect_files.py", payload, cwd=d)
            self.assertEqual((code, decision_of(out)), (0, "deny"))

    def test_write_to_a_normal_file_prints_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            payload = {"tool_name": "Write", "tool_input": {"file_path": "src/app.py"}}
            self.assertEqual(run_hook("protect_files.py", payload, cwd=d)[:2], (0, None))

    def test_read_is_not_this_hooks_business(self):
        with tempfile.TemporaryDirectory() as d:
            payload = {"tool_name": "Read", "tool_input": {"file_path": os.path.join(d, ".env")}}
            self.assertEqual(run_hook("protect_files.py", payload, cwd=d)[:2], (0, None))


if __name__ == "__main__":
    unittest.main()
