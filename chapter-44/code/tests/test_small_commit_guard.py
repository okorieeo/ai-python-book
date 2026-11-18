import os
import subprocess
import tempfile
import unittest

from hookutil import bash_payload, decision_of, run_hook

import small_commit_guard as scg


def fake_git(numstat_cached="", numstat_head=""):
    def run(argv):
        return numstat_head if argv[:2] == ["diff", "HEAD"] else numstat_cached
    return run


def rows(n_files, per_file=10):
    return "".join(f"{per_file}\t0\tfile{i}.py\n" for i in range(n_files))


class MessageRules(unittest.TestCase):
    def ev(self, cmd, git=None, **kw):
        return scg.evaluate(cmd, ".", git or fake_git(rows(2)), **kw)[0]

    def test_good_messages_pass(self):
        for m in ['git commit -m "feat(chat): rename a conversation"', 'git commit -m "fix: stop crediting twice"', "git commit -m 'test(billing): cover replays'",
                  'git commit -m "refactor(ai)!: drop the old client"', 'git commit --message="docs: explain the gate"', 'git commit -m"chore: bump"']:
            with self.subTest(m=m):
                self.assertIsNone(self.ev(m), m)

    def test_bad_messages_are_denied(self):
        for m in ['git commit -m "updates"', 'git commit -m "WIP"', 'git commit -m "Fix stuff"', 'git commit -m "feat add thing"', 'git commit -m "feat:"',
                  'git commit -m "feat: ' + "x" * 80 + '"', 'git commit -m "fix: done."', 'git commit -m ""']:
            with self.subTest(m=m):
                self.assertEqual(self.ev(m), "deny", m)

    def test_a_commit_with_no_message_is_denied_because_an_editor_cannot_open(self):
        self.assertEqual(self.ev("git commit"), "deny")

    def test_no_verify_is_always_denied(self):
        for m in ['git commit --no-verify -m "fix: x"', 'git commit -n -m "fix: x"', 'git commit -am "fix: x" --no-verify']:
            self.assertEqual(self.ev(m), "deny", m)

    def test_combined_flags_are_understood(self):
        self.assertIsNone(self.ev('git commit -am "fix: x"'))
        self.assertEqual(self.ev('git commit -am "nonsense"'), "deny")

    def test_amend_asks(self):
        self.assertEqual(self.ev('git commit --amend -m "fix: x"'), "ask")
        self.assertEqual(self.ev("git commit --amend --no-edit"), "ask")

    def test_only_the_first_message_is_the_subject(self):
        self.assertIsNone(self.ev('git commit -m "fix(chat): short subject" -m "A long body paragraph. It may end with a period."'))

    def test_other_commands_are_not_this_hooks_business(self):
        for c in ["git status", "git add -A", "ls", "echo git commit"]:
            self.assertIsNone(scg.evaluate(c, ".", fake_git())[0], c)

    def test_commit_inside_a_compound_command_is_found(self):
        self.assertEqual(self.ev('git add -A && git commit -m "nonsense"'), "deny")
        self.assertEqual(self.ev('cd repo && git -C . commit -m "nonsense"'), "deny")

    def test_a_file_or_reused_message_is_accepted_without_inspection(self):
        self.assertIsNone(self.ev("git commit -F msg.txt"))


class SizeRules(unittest.TestCase):
    OK = 'git commit -m "feat(chat): x"'

    def test_within_limits(self):
        self.assertIsNone(scg.evaluate(self.OK, ".", fake_git(rows(15, 40)))[0])             # 15 files, 600 lines: exactly the limit

    def test_too_many_files(self):
        kind, reason = scg.evaluate(self.OK, ".", fake_git(rows(16, 1)))
        self.assertEqual(kind, "deny")
        self.assertIn("16 files", reason)

    def test_too_many_lines(self):
        self.assertEqual(scg.evaluate(self.OK, ".", fake_git("500\t101\tbig.py\n"))[0], "deny")

    def test_binary_files_count_as_files_but_not_lines(self):
        self.assertIsNone(scg.evaluate(self.OK, ".", fake_git("-\t-\timage.png\n5\t5\ta.py\n"))[0])

    def test_dash_a_measures_the_whole_working_tree_not_just_the_index(self):
        git = fake_git(numstat_cached="", numstat_head=rows(20, 50))
        self.assertEqual(scg.evaluate('git commit -am "feat: x"', ".", git)[0], "deny")

    def test_limits_are_configurable(self):
        self.assertIsNone(scg.evaluate(self.OK, ".", fake_git(rows(30, 1)), max_files=50)[0])
        self.assertEqual(scg.evaluate(self.OK, ".", fake_git(rows(2, 10)), max_lines=5)[0], "deny")

    def test_an_empty_diff_is_left_for_git_to_complain_about(self):
        self.assertIsNone(scg.evaluate(self.OK, ".", fake_git(""))[0])


class AgainstRealGit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "Test")
        self.write("README.md", "hello\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "chore: start")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.d, check=True, capture_output=True)

    def write(self, name, text):
        path = os.path.join(self.d, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def hook(self, command, **env):
        return run_hook("small_commit_guard.py", bash_payload(command, self.d), cwd=self.d, env=env)

    def test_a_small_staged_change_is_allowed(self):
        self.write("a.py", "print(1)\n")
        self.git("add", "a.py")
        code, out, _ = self.hook('git commit -m "feat(core): add a"')
        self.assertEqual((code, out), (0, None))

    def test_a_pile_of_files_is_denied_with_advice_to_split(self):
        for i in range(20):
            self.write(f"src/f{i}.py", "x = 1\n")
        self.git("add", "-A")
        code, out, _ = self.hook('git commit -m "feat: everything"')
        self.assertEqual((code, decision_of(out)), (0, "deny"))
        self.assertIn("20 files", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIn("Split", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_unstaged_changes_do_not_count_without_dash_a(self):
        for i in range(20):
            self.write(f"src/f{i}.py", "x = 1\n")           # created but NOT staged
        code, out, _ = self.hook('git commit -m "feat: nothing staged"')
        self.assertIsNone(out)

    def test_dash_a_sees_modified_tracked_files(self):
        for i in range(20):
            self.write(f"t{i}.py", "x = 1\n")
        self.git("add", "-A"); self.git("commit", "-q", "-m", "chore: seed")
        for i in range(20):
            self.write(f"t{i}.py", "x = 2\n")
        code, out, _ = self.hook('git commit -am "fix: touch all"')
        self.assertEqual(decision_of(out), "deny")

    def test_the_environment_can_raise_the_limit(self):
        for i in range(20):
            self.write(f"src/f{i}.py", "x = 1\n")
        self.git("add", "-A")
        code, out, _ = self.hook('git commit -m "feat: big but allowed"', MAX_COMMIT_FILES="50")
        self.assertIsNone(out)

    def test_a_bad_message_is_denied_through_the_real_protocol(self):
        self.write("a.py", "x\n"); self.git("add", "a.py")
        self.assertEqual(decision_of(self.hook('git commit -m "wip"')[1]), "deny")


if __name__ == "__main__":
    unittest.main()
