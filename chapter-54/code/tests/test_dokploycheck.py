import http.server
import os
import threading
import time
import unittest

import yaml

from backend_snippets.health_checks import liveness, readiness
from dokploycheck import smoke
from dokploycheck.compose_lint import check_env_example, lint_compose, parse_env_example
from dokploycheck.findings import FAIL, PASS, WARN, worst_status

ROOT = os.path.dirname(os.path.dirname(__file__))
read = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()
by_name = lambda fs: {f.name: f for f in fs}


class ShippedFilesTests(unittest.TestCase):
    """The files we ship must pass our own checks."""

    def test_production_compose_has_no_problems(self):
        env = parse_env_example(read("deploy", ".env.production.example"))
        findings = lint_compose(read("deploy", "docker-compose.prod.yml"), env)
        self.assertEqual([f for f in findings if f.status != PASS], [])

    def test_env_example_contains_only_placeholders(self):
        findings = check_env_example(parse_env_example(read("deploy", ".env.production.example")))
        self.assertEqual(worst_status(findings), PASS)

    def test_every_secret_in_compose_uses_the_fail_fast_form(self):
        text = read("deploy", "docker-compose.prod.yml")
        for var in ("SECRET_KEY", "DATABASE_URL", "REDIS_URL", "STRIPE_SECRET_KEY", "PAYSTACK_SECRET_KEY", "LLM_API_KEY"):
            self.assertIn("${%s:?" % var, text)

    def test_migration_runs_before_the_app_and_only_once(self):
        svcs = yaml.safe_load(read("deploy", "docker-compose.prod.yml"))["services"]
        self.assertEqual(svcs["chat-migrate"]["restart"], "no")
        for name in ("chat-api", "chat-worker", "chat-beat", "chat-channels"):
            self.assertEqual(svcs[name]["depends_on"]["chat-migrate"]["condition"], "service_completed_successfully")

    def test_workflow_tests_before_deploy_and_never_cancels_a_running_deploy(self):
        wf = yaml.safe_load(read(".github", "workflows", "deploy.yml"))
        self.assertEqual(wf["jobs"]["deploy"]["needs"], "test")
        self.assertIs(wf["concurrency"]["cancel-in-progress"], False)
        self.assertEqual(wf["permissions"], {"contents": "read"})

    def test_web_build_args_are_public_values_only(self):
        build = yaml.safe_load(read("deploy", "docker-compose.prod.yml"))["services"]["chat-web"]["build"]
        self.assertTrue(all(k.startswith("NEXT_PUBLIC_") for k in build["args"]))


class LintBadComposeTests(unittest.TestCase):
    def setUp(self):
        env = parse_env_example(read("tests", "fixtures", "bad", "env.bad.example"))
        self.found = by_name(lint_compose(read("tests", "fixtures", "bad", "docker-compose.bad.yml"), env))

    def test_exposed_databases_fail(self):
        self.assertEqual(self.found["db ports"].status, FAIL)
        self.assertEqual(self.found["cache ports"].status, FAIL)

    def test_unpinned_images_fail(self):
        self.assertEqual(self.found["db image"].status, FAIL)
        self.assertEqual(self.found["cache image"].status, FAIL)

    def test_hardcoded_secrets_fail(self):
        self.assertEqual(self.found["db POSTGRES_PASSWORD"].status, FAIL)
        self.assertEqual(self.found["api SECRET_KEY"].status, FAIL)

    def test_secret_in_browser_bundle_fails(self):
        self.assertEqual(self.found["web NEXT_PUBLIC_STRIPE_SECRET_KEY"].status, FAIL)

    def test_docker_socket_fails_and_repo_bind_mount_warns(self):
        self.assertEqual(self.found["api docker.sock"].status, FAIL)
        self.assertEqual(self.found["api volume"].status, WARN)

    def test_missing_network_fails(self):
        self.assertEqual(self.found["compose network"].status, FAIL)

    def test_undefined_variable_fails(self):
        self.assertEqual(self.found["variable NOT_IN_EXAMPLE"].status, FAIL)

    def test_unguarded_secret_reference_warns(self):
        self.assertEqual(self.found["variable STRIPE_SECRET_KEY"].status, WARN)

    def test_container_name_and_missing_restart_warn(self):
        self.assertEqual(self.found["api container_name"].status, WARN)
        self.assertEqual(self.found["api restart"].status, WARN)

    def test_env_example_with_real_looking_secrets_fails(self):
        found = by_name(check_env_example(parse_env_example(read("tests", "fixtures", "bad", "env.bad.example"))))
        self.assertEqual(found["env example SECRET_KEY"].status, FAIL)
        self.assertEqual(found["env example STRIPE_SECRET_KEY"].status, FAIL)
        self.assertNotIn("env example LLM_API_KEY", found)

    def test_invalid_yaml_is_reported_not_raised(self):
        self.assertEqual(lint_compose("services: [unclosed")[0].status, FAIL)

    def test_isolated_mode_does_not_require_dokploy_network(self):
        text = "services:\n  web:\n    image: nginx:1.27\n    restart: unless-stopped\n"
        self.assertEqual(worst_status(lint_compose(text, isolated=True)), PASS)
        self.assertEqual(worst_status(lint_compose(text, isolated=False)), FAIL)


class HealthTests(unittest.TestCase):
    def test_liveness_never_depends_on_anything(self):
        self.assertEqual(liveness(), (200, {"status": "ok"}))

    def test_ready_when_all_checks_pass(self):
        self.assertEqual(readiness({"database": lambda: None, "redis": lambda: None})[0], 200)

    def test_failing_check_is_named_but_its_error_is_not_leaked(self):
        def boom():
            raise RuntimeError("password authentication failed for user chat at db-3f9a:5432")
        status, body = readiness({"database": boom, "redis": lambda: None})
        self.assertEqual(status, 503)
        self.assertEqual(body["failing"], ["database"])
        self.assertNotIn("password", str(body))

    def test_slow_check_counts_as_failing_and_does_not_hang(self):
        start = time.time()
        status, body = readiness({"redis": lambda: time.sleep(1.5)}, timeout=0.2)
        self.assertEqual((status, body["failing"]), (503, ["redis"]))
        self.assertLess(time.time() - start, 1.0)

    def test_no_checks_is_ready(self):
        self.assertEqual(readiness({})[0], 200)


def serve(responses):
    """Start a local HTTP server. responses: {path: (status, headers, body)}"""
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            status, headers, body = responses.get(self.path, (404, {}, b""))
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def stop(srv):
    srv.shutdown()
    srv.server_close()


class SmokeTests(unittest.TestCase):
    def test_redirect_to_https_passes_and_plain_200_fails(self):
        srv, port = serve({"/": (301, {"Location": "https://app.example.com/"}, b"")})
        self.addCleanup(stop, srv)
        self.assertEqual(smoke.check_https_redirect(f"https://127.0.0.1:{port}").status, PASS)
        srv2, port2 = serve({"/": (200, {}, b"hello")})
        self.addCleanup(stop, srv2)
        self.assertEqual(smoke.check_https_redirect(f"https://127.0.0.1:{port2}").status, FAIL)

    def test_temporary_redirect_is_only_a_warning(self):
        srv, port = serve({"/": (302, {"Location": "https://x.example.com/"}, b"")})
        self.addCleanup(stop, srv)
        self.assertEqual(smoke.check_https_redirect(f"https://127.0.0.1:{port}").status, WARN)

    def test_ready_endpoint(self):
        srv, port = serve({"/health/ready": (200, {}, b'{"status":"ok"}')})
        self.addCleanup(stop, srv)
        self.assertEqual(smoke.check_ready(f"http://127.0.0.1:{port}").status, PASS)
        srv2, port2 = serve({"/health/ready": (503, {}, b'{"status":"unavailable","failing":["redis"]}')})
        self.addCleanup(stop, srv2)
        f = smoke.check_ready(f"http://127.0.0.1:{port2}")
        self.assertEqual(f.status, FAIL)
        self.assertIn("redis", f.detail)

    def test_connection_refused_is_a_failure_not_a_crash(self):
        self.assertEqual(smoke.check_ready("http://127.0.0.1:1").status, FAIL)

    def test_security_headers(self):
        srv, port = serve({"/": (200, {"Strict-Transport-Security": "max-age=300", "X-Content-Type-Options": "nosniff"}, b"")})
        self.addCleanup(stop, srv)
        self.assertEqual(worst_status(smoke.check_headers(f"http://127.0.0.1:{port}/")), PASS)
        srv2, port2 = serve({"/": (200, {}, b"")})
        self.addCleanup(stop, srv2)
        self.assertEqual(worst_status(smoke.check_headers(f"http://127.0.0.1:{port2}/")), WARN)

    def test_wait_mode_retries_until_the_new_version_answers(self):
        state = {"n": 0}
        calls = []
        real = smoke.run
        def flaky(app, api):
            state["n"] += 1
            calls.append(state["n"])
            return [smoke.Finding("x", FAIL if state["n"] < 3 else PASS, "")]
        smoke.run = flaky
        real_sleep = smoke.time.sleep
        smoke.time.sleep = lambda s: None
        try:
            self.assertEqual(smoke.main(["--app", "https://a", "--api", "https://b", "--wait", "60"]), 0)
        finally:
            smoke.run, smoke.time.sleep = real, real_sleep
        self.assertEqual(calls, [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
