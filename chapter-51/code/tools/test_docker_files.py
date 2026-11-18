"""Tests for Chapter 51: the Dockerfile checker, the real Dockerfiles, and the helper scripts.

None of these tests needs Docker. Run from the repository root:

    python -m unittest discover -s tools -v
"""
from __future__ import annotations

import contextlib
import http.server
import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "backend" / "docker"))

import dockerlint  # noqa: E402
import healthcheck  # noqa: E402
import wait_for  # noqa: E402


def rules(text: str) -> set[str]:
    return {f.rule for f in dockerlint.lint_dockerfile(text)}


GOOD = """\
# syntax=docker/dockerfile:1
FROM python:3.13-slim AS builder
RUN apt-get update \\
 && apt-get install -y --no-install-recommends build-essential \\
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.13-slim
COPY --from=builder /usr/local /usr/local
WORKDIR /app
COPY . .
USER 10001
HEALTHCHECK CMD ["true"]
CMD ["python", "app.py"]
"""


class DockerfileRuleTests(unittest.TestCase):
    def test_a_good_dockerfile_has_no_findings(self):
        self.assertEqual(dockerlint.lint_dockerfile(GOOD), [])

    def test_line_continuations_and_comments_are_parsed(self):
        items = dockerlint.parse_instructions("RUN a \\\n  # comment\n  && b\n# alone\nUSER x\n")
        self.assertEqual([(i.name, i.line) for i in items], [("RUN", 1), ("USER", 5)])
        self.assertEqual(items[0].args, "a && b")

    def test_dl001_missing_and_latest_tags(self):
        self.assertIn("DL001", rules(GOOD.replace("python:3.13-slim AS", "python AS")))
        self.assertIn("DL001", rules(GOOD.replace("python:3.13-slim AS", "python:latest AS")))

    def test_dl001_allows_digests_build_args_and_stage_names(self):
        digest = "python@sha256:" + "a" * 64
        self.assertNotIn("DL001", rules(GOOD.replace("python:3.13-slim AS", f"{digest} AS")))
        self.assertNotIn("DL001", rules(GOOD.replace("python:3.13-slim AS", "python:${PY}-slim AS")))
        staged = GOOD.replace("FROM python:3.13-slim\n", "FROM builder\n")
        self.assertNotIn("DL001", rules(staged))

    def test_dl001_registry_port_is_not_mistaken_for_a_tag(self):
        self.assertIn("DL001", rules(GOOD.replace("python:3.13-slim AS", "localhost:5000/python AS")))

    def test_dl002_root_user(self):
        self.assertIn("DL002", rules(GOOD.replace("USER 10001\n", "")))
        self.assertIn("DL002", rules(GOOD.replace("USER 10001", "USER root")))
        self.assertIn("DL002", rules(GOOD.replace("USER 10001", "USER 0:0")))

    def test_dl003_single_stage(self):
        single = "FROM python:3.13-slim\nUSER 1000\nHEALTHCHECK CMD [\"true\"]\nCMD [\"x\"]\n"
        self.assertIn("DL003", rules(single))

    def test_dl004_apt_hygiene(self):
        base = "FROM python:3.13-slim AS b\n%s\nFROM python:3.13-slim\nUSER 1\nHEALTHCHECK CMD [\"x\"]\n"
        no_flag = base % "RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*"
        no_clean = base % "RUN apt-get update && apt-get install -y --no-install-recommends gcc"
        stale = base % "RUN apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*"
        update_alone = base % "RUN apt-get update"
        for text in (no_flag, no_clean, stale, update_alone):
            self.assertIn("DL004", rules(text), text)

    def test_dl005_copy_everything_before_installing(self):
        bad = GOOD.replace("COPY requirements.txt .\n", "COPY . .\n")
        self.assertIn("DL005", rules(bad))

    def test_dl005_is_not_triggered_by_copy_after_install(self):
        self.assertNotIn("DL005", rules(GOOD))

    def test_dl006_secrets_in_env_and_arg(self):
        for line in ("ENV DJANGO_SECRET_KEY=abc", "ARG DB_PASSWORD", "ENV API_TOKEN abc",
                     "ENV A=1 STRIPE_API_KEY=sk_live_x"):
            self.assertIn("DL006", rules(GOOD.replace("WORKDIR /app", f"WORKDIR /app\n{line}")), line)

    def test_dl006_allows_public_names_and_file_paths(self):
        for line in ("ARG NEXT_PUBLIC_API_KEY", "ENV DJANGO_SECRET_KEY_FILE=/run/secrets/key",
                     "ENV PYTHONUNBUFFERED=1"):
            self.assertNotIn("DL006", rules(GOOD.replace("WORKDIR /app", f"WORKDIR /app\n{line}")), line)

    def test_dl007_healthcheck(self):
        self.assertIn("DL007", rules(GOOD.replace('HEALTHCHECK CMD ["true"]\n', "")))
        self.assertIn("DL007", rules(GOOD.replace('HEALTHCHECK CMD ["true"]', "HEALTHCHECK NONE")))

    def test_dl008_shell_form_cmd_and_entrypoint(self):
        self.assertIn("DL008", rules(GOOD.replace('CMD ["python", "app.py"]', "CMD python app.py")))
        self.assertIn("DL008", rules(GOOD + "ENTRYPOINT ./start.sh\n"))

    def test_dl009_env_files_and_add(self):
        self.assertIn("DL009", rules(GOOD.replace("WORKDIR /app", "WORKDIR /app\nCOPY .env .")))
        self.assertIn("DL009", rules(GOOD.replace("WORKDIR /app", "WORKDIR /app\nCOPY config/.env.production /x")))
        self.assertNotIn("DL009", rules(GOOD.replace("WORKDIR /app", "WORKDIR /app\nCOPY .env.example .")))
        self.assertIn("DL009", rules(GOOD.replace("WORKDIR /app", "WORKDIR /app\nADD app.py /app/")))
        self.assertNotIn("DL009", rules(GOOD.replace("WORKDIR /app", "WORKDIR /app\nADD https://example.com/f /f")))

    def test_dl010_pip_cache(self):
        bad = GOOD.replace("pip install --no-cache-dir", "pip install")
        self.assertIn("DL010", rules(bad))
        cached = GOOD.replace("RUN pip install --no-cache-dir", "RUN --mount=type=cache,target=/root/.cache/pip pip install")
        self.assertNotIn("DL010", rules(cached))

    def test_empty_file_is_reported(self):
        self.assertEqual([f.rule for f in dockerlint.lint_dockerfile("# nothing\n")], ["DL000"])


class DockerignoreTests(unittest.TestCase):
    def test_real_ignore_files_pass_for_their_kind(self):
        backend = (ROOT / "backend" / ".dockerignore").read_text()
        frontend = (ROOT / "frontend" / ".dockerignore").read_text()
        self.assertEqual(dockerlint.lint_dockerignore(backend, "python"), [])
        self.assertEqual(dockerlint.lint_dockerignore(frontend, "node"), [])

    def test_missing_entries_are_reported(self):
        messages = " ".join(str(f) for f in dockerlint.lint_dockerignore("__pycache__\n", "python"))
        self.assertIn(".env", messages)
        self.assertIn(".git", messages)
        self.assertIn(".venv", messages)

    def test_wildcard_env_pattern_counts(self):
        text = ".env*\n.git\n.venv\n__pycache__\n"
        self.assertEqual(dockerlint.lint_dockerignore(text, "python"), [])

    def test_reincluding_other_paths_is_flagged(self):
        text = ".env\n.git\n!.env.local\n!.env.example\n"
        found = dockerlint.lint_dockerignore(text)
        self.assertEqual([f.rule for f in found], ["DI002"])
        self.assertEqual(found[0].line, 3)


class RealDockerfileTests(unittest.TestCase):
    def test_backend_and_frontend_dockerfiles_follow_the_rules(self):
        for path in ("backend/Dockerfile", "frontend/Dockerfile"):
            text = (ROOT / path).read_text()
            self.assertEqual(dockerlint.lint_dockerfile(text), [], path)

    def test_backend_is_multistage_and_runs_as_a_named_user(self):
        text = (ROOT / "backend" / "Dockerfile").read_text()
        _, stages = dockerlint.split_stages(dockerlint.parse_instructions(text))
        self.assertEqual([s.name for s in stages], ["builder", "runtime"])
        self.assertIn("USER app", text)

    def test_frontend_has_three_stages_and_standalone_output(self):
        text = (ROOT / "frontend" / "Dockerfile").read_text()
        _, stages = dockerlint.split_stages(dockerlint.parse_instructions(text))
        self.assertEqual([s.name for s in stages], ["deps", "builder", "runner"])
        self.assertIn('output: "standalone"', (ROOT / "frontend" / "next.config.ts").read_text())

    def test_command_line_exit_codes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(dockerlint.main([str(ROOT / "backend" / "Dockerfile")]), 0)
            with tempfile.TemporaryDirectory() as tmp:
                bad = Path(tmp) / "Dockerfile"
                bad.write_text("FROM python\nCMD python x.py\n")
                self.assertEqual(dockerlint.main([str(bad)]), 1)
            self.assertEqual(dockerlint.main([str(ROOT / "nope" / "Dockerfile")]), 1)


def listening_socket():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(5)
    return server, server.getsockname()[1]


def free_port() -> int:
    server, port = listening_socket()
    server.close()
    return port


class WaitForTests(unittest.TestCase):
    def test_parse_target(self):
        self.assertEqual(wait_for.parse_target("db:5432"), ("db", 5432))
        self.assertEqual(wait_for.parse_target("::1:80"), ("::1", 80))
        for bad in ("db", "db:", ":5432", "db:port"):
            with self.assertRaises(ValueError):
                wait_for.parse_target(bad)

    def test_returns_true_when_the_service_is_up(self):
        server, port = listening_socket()
        self.addCleanup(server.close)
        sink = []

        class Out:
            def write(self, text):
                sink.append(text)

            def flush(self):
                pass

        self.assertTrue(wait_for.wait_for([("127.0.0.1", port)], timeout=2, interval=0.05, out=Out()))
        self.assertIn("accepting connections", "".join(sink))

    def test_returns_false_after_the_timeout(self):
        started = __import__("time").monotonic()
        self.assertFalse(wait_for.wait_for([("127.0.0.1", free_port())], timeout=0.3, interval=0.05,
                                           out=io.StringIO()))
        self.assertLess(__import__("time").monotonic() - started, 3)

    def test_waits_for_a_service_that_starts_late(self):
        port = free_port()
        holder = {}

        def start_later():
            __import__("time").sleep(0.4)
            server = socket.socket()
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", port))
            server.listen(1)
            holder["server"] = server

        thread = threading.Thread(target=start_later)
        thread.start()
        try:
            self.assertTrue(wait_for.wait_for([("127.0.0.1", port)], timeout=5, interval=0.1,
                                              out=io.StringIO()))
        finally:
            thread.join()
            holder["server"].close()

    def test_main_exit_codes_and_bad_input(self):
        server, port = listening_socket()
        self.addCleanup(server.close)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(wait_for.main([f"127.0.0.1:{port}", "--timeout", "2"]), 0)
            self.assertEqual(wait_for.main([f"127.0.0.1:{free_port()}", "--timeout", "0.2", "--interval", "0.05"]), 1)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            wait_for.main(["not-a-target"])


class _Handler(http.server.BaseHTTPRequestHandler):
    seen: dict = {}

    def do_GET(self):  # noqa: N802
        type(self).seen = {"host": self.headers.get("Host"), "proto": self.headers.get("X-Forwarded-Proto")}
        if self.path == "/ok":
            self.send_response(200)
        elif self.path == "/redirect":
            self.send_response(301)
            self.send_header("Location", "https://example.com/")
        elif self.path == "/bad-host":
            self.send_response(400)
        else:
            self.send_response(500)
        self.end_headers()
        self.wfile.write(b"x")

    def log_message(self, *args):
        pass


class HealthcheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_200_is_healthy(self):
        self.assertEqual(healthcheck.check(self.url("/ok")), (True, "healthy"))

    def test_sends_the_configured_host_header_and_forwarded_proto(self):
        healthcheck.check(self.url("/ok"), host="app.example.com")
        self.assertEqual(_Handler.seen, {"host": "app.example.com", "proto": "https"})

    def test_a_redirect_is_not_followed_and_counts_as_unhealthy(self):
        self.assertEqual(healthcheck.check(self.url("/redirect")), (False, "HTTP 301"))

    def test_error_statuses_are_unhealthy(self):
        self.assertEqual(healthcheck.check(self.url("/bad-host")), (False, "HTTP 400"))
        self.assertEqual(healthcheck.check(self.url("/boom")), (False, "HTTP 500"))

    def test_nothing_listening_is_unhealthy(self):
        ok, message = healthcheck.check(f"http://127.0.0.1:{free_port()}/ok", timeout=1)
        self.assertFalse(ok)
        self.assertIn("cannot connect", message)

    def test_main_uses_environment_variables(self):
        old = {k: os.environ.get(k) for k in ("PORT", "HEALTHCHECK_PATH", "HEALTHCHECK_HOST")}
        try:
            os.environ.update(PORT=str(self.port), HEALTHCHECK_PATH="/ok", HEALTHCHECK_HOST="x.test")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(healthcheck.main(), 0)
                os.environ["HEALTHCHECK_PATH"] = "/boom"
                self.assertEqual(healthcheck.main(), 1)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


@unittest.skipUnless(shutil.which("sh"), "needs a POSIX shell")
class EntrypointTests(unittest.TestCase):
    """Runs backend/docker/entrypoint.sh with a fake 'python' that records its arguments."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.log = Path(self.tmp) / "python-calls.txt"
        fake = Path(self.tmp) / "python"
        fake.write_text(f'#!/bin/sh\necho "$@" >> "{self.log}"\n')
        fake.chmod(0o755)

    def run_entry(self, *command, **env):
        full_env = {"PATH": f"{self.tmp}:{os.environ['PATH']}", "HOME": self.tmp}
        full_env.update(env)
        return subprocess.run(
            ["sh", str(ROOT / "backend" / "docker" / "entrypoint.sh"), *command],
            env=full_env, cwd=self.tmp, capture_output=True, text=True, timeout=30,
        )

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_the_script_is_valid_posix_sh(self):
        result = subprocess.run(["sh", "-n", str(ROOT / "backend" / "docker" / "entrypoint.sh")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_runs_the_command_and_keeps_arguments_intact(self):
        result = self.run_entry("printf", "%s|", "a b", "c")
        self.assertEqual(result.stdout, "a b|c|")
        self.assertEqual(self.calls(), [])

    def test_exit_code_of_the_command_is_passed_through(self):
        self.assertEqual(self.run_entry("sh", "-c", "exit 3").returncode, 3)

    def test_no_command_is_an_error_not_a_hang(self):
        self.assertNotEqual(self.run_entry().returncode, 0)

    def test_wait_for_is_called_with_the_targets_and_timeout(self):
        result = self.run_entry("echo", "up", WAIT_FOR="db:5432 redis:6379", WAIT_FOR_TIMEOUT="7")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(self.calls()), 1)
        self.assertTrue(self.calls()[0].endswith("wait_for.py --timeout 7 db:5432 redis:6379"))

    def test_a_failed_wait_stops_the_container_before_the_command_runs(self):
        fake = Path(self.tmp) / "python"
        fake.write_text("#!/bin/sh\nexit 1\n")
        result = self.run_entry("echo", "should-not-print", WAIT_FOR="db:5432")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("should-not-print", result.stdout)

    def test_migrations_only_run_when_asked(self):
        self.run_entry("true")
        self.assertEqual(self.calls(), [])
        self.run_entry("true", RUN_MIGRATIONS="true")
        self.assertEqual(self.calls(), ["manage.py migrate --noinput"])
        self.log.unlink()
        self.run_entry("true", RUN_MIGRATIONS="false")
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
