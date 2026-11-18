"""Tests for Chapter 55's backup script and retention policy. No Docker, age or rclone needed.

    python3 -m unittest discover -s ops -v
"""
import contextlib
import io
import os
import stat
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backup  # noqa: E402
import retention  # noqa: E402

D = lambda s: datetime.strptime(s, "%Y%m%d-%H%M%S")  # noqa: E731


class RetentionTests(unittest.TestCase):
    def test_parse_stamp(self):
        self.assertEqual(retention.parse_stamp("chat-20261110-031500.dump.age"), datetime(2026, 11, 10, 3, 15))
        self.assertEqual(retention.parse_stamp("chat-20261110-031500.dump"), datetime(2026, 11, 10, 3, 15))
        for bad in ("notes.txt", "chat-2026.dump", "chat-20261110-031500.sql", ".hidden", "chat-20261110-031500.dump.age.tmp"):
            self.assertIsNone(retention.parse_stamp(bad), bad)

    def make(self, start: date, days: int, per_day=1):
        names = []
        for i in range(days):
            day = start - timedelta(days=i)
            for h in range(per_day):
                names.append(f"chat-{day:%Y%m%d}-{3 + h:02d}1500.dump.age")
        return names

    def test_a_short_history_is_kept_whole(self):
        names = self.make(date(2026, 11, 10), 5)
        keep, delete = retention.plan_prune(names, date(2026, 11, 10))
        self.assertEqual(delete, [])
        self.assertEqual(len(keep), 5)

    def test_long_history_keeps_daily_weekly_and_monthly(self):
        today = date(2026, 11, 10)
        names = self.make(today, 400)
        keep, delete = retention.plan_prune(names, today)
        kept_days = {retention.parse_stamp(n).date() for n in keep}
        for i in range(7):
            self.assertIn(today - timedelta(days=i), kept_days)
        self.assertLess(len(keep), 7 + 4 + 6 + 1)
        self.assertEqual(len(keep) + len(delete), 400)
        self.assertGreater(len(delete), 380)
        months = {(d.year, d.month) for d in kept_days}
        self.assertEqual(len([m for m in months if m >= (2026, 5)]), 6)

    def test_the_newest_of_a_day_wins(self):
        names = ["chat-20261110-031500.dump.age", "chat-20261110-151500.dump.age"]
        keep, delete = retention.plan_prune(names, date(2026, 11, 10), daily=1, weekly=0, monthly=0)
        self.assertEqual((keep, delete), (["chat-20261110-151500.dump.age"], ["chat-20261110-031500.dump.age"]))

    def test_unknown_files_are_never_touched(self):
        names = ["README.txt", "chat-20200101-000000.dump.age", "chat-20261110-031500.dump.age", "other.dump.bak"]
        keep, delete = retention.plan_prune(names, date(2026, 11, 10))
        self.assertNotIn("README.txt", keep + delete)
        self.assertNotIn("other.dump.bak", keep + delete)

    def test_the_newest_backup_survives_even_if_very_old(self):
        keep, delete = retention.plan_prune(["chat-20200101-000000.dump.age"], date(2026, 11, 10))
        self.assertEqual((keep, delete), (["chat-20200101-000000.dump.age"], []))

    def test_empty_and_year_boundary(self):
        self.assertEqual(retention.plan_prune([], date(2026, 11, 10)), ([], []))
        self.assertEqual(retention._months_back(date(2026, 1, 15), 1), (2025, 12))
        self.assertEqual(retention._months_back(date(2026, 3, 1), 14), (2025, 1))
        names = ["chat-20251215-031500.dump.age", "chat-20260102-031500.dump.age"]
        keep, _ = retention.plan_prune(names, date(2026, 1, 3), daily=1, weekly=0, monthly=2)
        self.assertEqual(len(keep), 2)


class Recorder:
    """A stand-in for subprocess: records each command and writes what the real tool would."""

    def __init__(self, fail_on=None, dump_bytes=4096, listing="; Archive\n123; 0 1 TABLE DATA public auth_user chat\n"):
        self.calls, self.fail_on, self.dump_bytes, self.listing = [], fail_on, dump_bytes, listing

    def __call__(self, cmd, *, cwd=None, stdin=None, stdout=None):
        self.calls.append(cmd)
        tool = cmd[0] if cmd[0] != "docker" else ("pg_dump" if "sh" in cmd else "pg_restore")
        if tool == self.fail_on:
            return 1
        if tool == "pg_dump":
            Path(stdout).write_bytes(b"x" * self.dump_bytes)
        elif tool == "pg_restore":
            Path(stdout).write_text(self.listing)
        elif tool == "age":
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"encrypted")
        return 0


class FakeHeartbeat:
    events = []

    def __init__(self, url):
        self.url = url

    def __enter__(self):
        type(self).events.append(("start", self.url))

    def __exit__(self, exc_type, exc, tb):
        type(self).events.append(("fail" if exc_type else "ok", self.url))
        return False


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / "backups"
        FakeHeartbeat.events = []

    def cfg(self, **kw):
        base = dict(compose_dir=Path(self.tmp.name), backup_dir=self.dir, age_recipient="age1abc",
                    heartbeat_url="https://hc/x")
        base.update(kw)
        return backup.Config(**base)

    def go(self, run=None, **kw):
        run = run or Recorder()
        path = backup.run_backup(self.cfg(**kw), run=run, now=lambda: datetime(2026, 11, 10, 3, 15), heartbeat_fn=FakeHeartbeat)
        return path, run

    def test_command_builders(self):
        self.assertEqual(backup.build_dump_command("db")[:5], ["docker", "compose", "exec", "-T", "db"])
        self.assertIn('pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"', backup.build_dump_command("db")[-1])
        self.assertEqual(backup.build_verify_command("db")[-2:], ["pg_restore", "--list"])
        self.assertEqual(backup.build_encrypt_command("age1k", Path("a"), Path("b")), ["age", "-r", "age1k", "-o", "b", "a"])
        self.assertEqual(backup.build_upload_command("b2:bucket/x/", Path("/t/f.age")), ["rclone", "copyto", "/t/f.age", "b2:bucket/x/f.age"])

    def test_the_happy_path_order_and_result(self):
        path, run = self.go(rclone_remote="b2:bucket/ai-chat")
        self.assertEqual(path.name, "chat-20261110-031500.dump.age")
        tools = [c[0] if c[0] != "docker" else c[5] if c[5] != "sh" else "pg_dump" for c in run.calls]
        self.assertEqual(tools, ["pg_dump", "pg_restore", "age", "rclone"])
        self.assertEqual(FakeHeartbeat.events, [("start", "https://hc/x"), ("ok", "https://hc/x")])

    def test_no_plaintext_dump_or_listing_is_left_behind(self):
        self.go()
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["chat-20261110-031500.dump.age"])

    def test_permissions_are_private(self):
        path, _ = self.go()
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.dir).st_mode), 0o700)

    def test_refuses_to_upload_without_encryption(self):
        run = Recorder()
        with self.assertRaises(backup.BackupError):
            self.go(run=run, age_recipient=None, rclone_remote="b2:bucket")
        self.assertEqual(run.calls, [])

    def test_local_only_unencrypted_keeps_the_dump(self):
        path, _ = self.go(age_recipient=None)
        self.assertEqual(path.name, "chat-20261110-031500.dump")
        self.assertTrue(path.exists())

    def test_each_failure_stops_the_chain_cleans_up_and_signals_fail(self):
        for tool, message in (("pg_dump", "pg_dump failed"), ("pg_restore", "restorable"), ("age", "encryption failed"),
                              ("rclone", "offsite copy failed")):
            FakeHeartbeat.events = []
            run = Recorder(fail_on=tool)
            with self.assertRaises(backup.BackupError) as caught:
                self.go(run=run, rclone_remote="b2:bucket")
            self.assertIn(message, str(caught.exception))
            self.assertEqual(FakeHeartbeat.events[-1][0], "fail", tool)
            leftovers = [p.name for p in self.dir.iterdir()]
            self.assertFalse(any(n.endswith(".dump") or n.startswith(".") for n in leftovers), (tool, leftovers))
            if tool != "rclone":
                self.assertEqual([c for c in run.calls if c[0] == "rclone"], [])

    def test_a_tiny_dump_is_rejected(self):
        with self.assertRaises(backup.BackupError) as caught:
            self.go(run=Recorder(dump_bytes=10))
        self.assertIn("suspiciously small", str(caught.exception))

    def test_a_dump_with_no_table_data_is_rejected(self):
        with self.assertRaises(backup.BackupError):
            self.go(run=Recorder(listing="; Archive created\n"))

    def test_a_missing_tool_counts_as_failure_not_a_crash(self):
        self.assertEqual(backup.default_runner(["definitely-not-a-real-command-xyz"]), 127)

    def test_old_backups_are_pruned_but_only_after_success(self):
        self.dir.mkdir(parents=True)
        old = [f"chat-{(date(2026, 11, 10) - timedelta(days=i)):%Y%m%d}-031500.dump.age" for i in range(1, 120)]
        for name in old:
            (self.dir / name).write_bytes(b"e")
        (self.dir / "notes.txt").write_text("keep me")
        before = set(os.listdir(self.dir))
        with self.assertRaises(backup.BackupError):
            self.go(run=Recorder(fail_on="age"))
        self.assertEqual(set(os.listdir(self.dir)), before)  # failure: nothing pruned
        self.go()
        after = set(os.listdir(self.dir))
        self.assertIn("notes.txt", after)
        self.assertIn("chat-20261110-031500.dump.age", after)
        self.assertLess(len(after), 40)

    def test_main_reads_the_environment_and_returns_exit_codes(self):
        env = {"BACKUP_AGE_RECIPIENT": "age1abc"}
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ok = backup.main(["--compose-dir", self.tmp.name, "--backup-dir", str(self.dir)], environ=env, run=Recorder())
            bad = backup.main(["--compose-dir", self.tmp.name, "--backup-dir", str(self.dir)], environ=env, run=Recorder(fail_on="pg_dump"))
        self.assertEqual((ok, bad), (0, 1))
        self.assertIn("BACKUP OK", out.getvalue())
        self.assertIn("BACKUP FAILED: pg_dump failed", err.getvalue())

    def test_main_refuses_an_offsite_copy_without_a_key(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = backup.main(["--backup-dir", str(self.dir)], environ={"BACKUP_RCLONE_REMOTE": "b2:x"}, run=Recorder())
        self.assertEqual(code, 1)
        self.assertIn("unencrypted", err.getvalue())


class CheckLogsScriptTests(unittest.TestCase):
    """Runs ops/check_logs.sh with stand-ins for docker and curl on the PATH."""

    def setUp(self):
        import json
        import subprocess
        self.subprocess = subprocess
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        bin_dir = Path(self.tmp.name)
        self.curl_log = bin_dir / "curl.log"
        (bin_dir / "docker").write_text('#!/bin/sh\ncat "$FAKE_LOGS"\n')
        (bin_dir / "curl").write_text(
            '#!/bin/sh\necho "$@" >> "$CURL_LOG"\n'
            'for a in "$@"; do case "$a" in @*) cat "${a#@}" >> "$CURL_LOG";; esac; done\n')
        for name in ("docker", "curl"):
            os.chmod(bin_dir / name, 0o755)
        self.json = json
        self.bin_dir = bin_dir

    def run_script(self, statuses, url="https://hc.example/abc", with_url=True):
        line = lambda s: self.json.dumps({"event": "http_request", "fields": {"status": s, "ms": 5, "user_id": "u"}})  # noqa: E731
        logs = self.bin_dir / "logs.txt"
        logs.write_text("\n".join("backend-1  | " + line(s) for s in statuses) + "\n")
        env = {"PATH": f"{self.bin_dir}:{os.environ['PATH']}", "FAKE_LOGS": str(logs), "CURL_LOG": str(self.curl_log)}
        if with_url:
            env["LOGALERTS_PING_URL"] = url
        return self.subprocess.run(["sh", str(Path(__file__).resolve().parent / "check_logs.sh")],
                                   env=env, capture_output=True, text=True, timeout=30)

    def test_quiet_logs_send_a_success_ping(self):
        result = self.run_script([200] * 60)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.curl_log.read_text().splitlines()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].endswith("https://hc.example/abc"))
        self.assertNotIn("/fail", calls[0])

    def test_alerts_send_a_fail_ping_with_the_alert_text(self):
        result = self.run_script([429] * 60)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.curl_log.read_text()
        self.assertIn("https://hc.example/abc/fail", text)
        self.assertIn("ALERT rate_limited: 60", text)

    def test_a_missing_ping_url_is_an_error(self):
        result = self.run_script([200], with_url=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LOGALERTS_PING_URL", result.stderr)
        self.assertFalse(self.curl_log.exists())

    def test_the_script_is_valid_posix_sh(self):
        result = self.subprocess.run(["sh", "-n", str(Path(__file__).resolve().parent / "check_logs.sh")],
                                     capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
