"""Tests for Chapter 52: the Compose files and the Compose policy checker. No Docker needed.

    python -m unittest discover -s tools -v        (needs PyYAML)
"""
from __future__ import annotations

import contextlib
import copy
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import composelint as cl  # noqa: E402


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


BASE, DEV, PROD, SECRETS = (read(n) for n in ("compose.yaml", "compose.dev.yaml", "compose.prod.yaml", "compose.secrets.yaml"))
ENV = read(".env.example")


def rules(findings) -> set[str]:
    return {f.rule for f in findings}


class RealFilesTests(unittest.TestCase):
    def test_every_file_is_valid_yaml_with_the_expected_services(self):
        base = cl.load(BASE)
        self.assertEqual(set(base["services"]), {
            "db", "redis", "migrate", "backend", "channels-worker", "celery-worker", "celery-beat", "frontend"})
        self.assertEqual(set(base["volumes"]), {"pgdata", "redisdata", "media"})
        self.assertNotIn("version", base)

    def test_the_command_line_checker_passes_on_the_real_files(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cl.main([str(ROOT)]), 0)
        self.assertTrue(out.getvalue().startswith("OK"))

    def test_base_publishes_no_ports(self):
        for name, svc in cl.load(BASE)["services"].items():
            self.assertFalse(svc.get("ports"), name)

    def test_django_family_shares_one_image_and_only_backend_builds(self):
        services = cl.load(BASE)["services"]
        images = {services[n]["image"] for n in ("migrate", "backend", "channels-worker", "celery-worker", "celery-beat")}
        self.assertEqual(len(images), 1)
        for name in ("migrate", "channels-worker", "celery-worker", "celery-beat"):
            self.assertNotIn("build", services[name], name)
        self.assertIn("build", services["backend"])

    def test_the_anchor_gives_every_django_service_the_same_environment(self):
        services = cl.load(BASE)["services"]
        envs = [services[n]["environment"] for n in ("migrate", "backend", "celery-worker", "celery-beat")]
        self.assertTrue(all(e == envs[0] for e in envs))
        self.assertIn("DATABASE_URL", envs[0])
        self.assertTrue(envs[0]["DATABASE_URL"].split("@")[1].startswith("db:5432"))
        self.assertEqual(envs[0]["REDIS_URL"], "redis://redis:6379/0")

    def test_start_up_order_matches_the_chapter(self):
        s = cl.load(BASE)["services"]
        cond = lambda svc, dep: s[svc]["depends_on"][dep]["condition"]  # noqa: E731
        self.assertEqual(cond("migrate", "db"), "service_healthy")
        self.assertEqual(cond("backend", "migrate"), "service_completed_successfully")
        self.assertEqual(cond("backend", "redis"), "service_healthy")
        self.assertEqual(cond("celery-worker", "migrate"), "service_completed_successfully")
        self.assertEqual(cond("celery-beat", "redis"), "service_healthy")
        self.assertEqual(cond("frontend", "backend"), "service_healthy")

    def test_migrate_is_a_one_shot_that_never_restarts(self):
        m = cl.load(BASE)["services"]["migrate"]
        self.assertEqual(m["restart"], "no")
        self.assertEqual(m["command"][:3], ["python", "manage.py", "migrate"])
        merged = cl.merge_files(BASE, PROD)["services"]["migrate"]
        self.assertEqual(merged["restart"], "no")

    def test_postgres_volume_uses_the_version_18_path(self):
        self.assertIn("pgdata:/var/lib/postgresql", cl.load(BASE)["services"]["db"]["volumes"])

    def test_healthcheck_dollar_signs_are_escaped(self):
        s = cl.load(BASE)["services"]
        self.assertIn("$${POSTGRES_USER}", s["db"]["healthcheck"]["test"][1])
        self.assertIn("$$HOSTNAME", s["celery-worker"]["healthcheck"]["test"][1])

    def test_only_one_beat_and_the_channels_worker_is_optional(self):
        s = cl.load(BASE)["services"]
        self.assertEqual(s["channels-worker"]["profiles"], ["channels"])
        self.assertNotIn("replicas", s["celery-beat"].get("deploy", {}))


class MergedViewTests(unittest.TestCase):
    def test_dev_merge_binds_ports_to_localhost_and_appends_volumes(self):
        dev = cl.merge_files(BASE, DEV)["services"]
        self.assertEqual(dev["backend"]["ports"], ["127.0.0.1:8000:8000"])
        self.assertEqual(dev["backend"]["volumes"], ["media:/app/media", "./backend:/app"])
        self.assertEqual(dev["backend"]["environment"]["DJANGO_DEBUG"], "true")
        self.assertIn("--reload", dev["backend"]["command"])
        self.assertEqual(dev["frontend"]["profiles"], ["with-frontend"])

    def test_prod_merge_has_restart_logging_and_hardening_everywhere(self):
        prod = cl.merge_files(BASE, PROD)["services"]
        for name in ("db", "redis", "backend", "celery-worker", "celery-beat", "frontend"):
            self.assertEqual(prod[name]["restart"], "unless-stopped", name)
            self.assertEqual(prod[name]["logging"]["options"]["max-size"], "10m", name)
            self.assertIn("no-new-privileges:true", prod[name]["security_opt"], name)
        for name in ("backend", "celery-worker", "celery-beat", "frontend", "migrate"):
            self.assertIn("ALL", prod[name]["cap_drop"], name)
        for name in ("db", "redis"):
            self.assertNotIn("cap_drop", prod[name], name)  # their entrypoints need capabilities
        for name, svc in prod.items():
            self.assertFalse(svc.get("ports"), name)

    def test_secrets_overlay_adds_the_file_secret_to_every_django_service(self):
        merged = cl.merge_files(BASE, PROD, SECRETS)
        for name in ("migrate", "backend", "celery-worker", "celery-beat", "channels-worker"):
            svc = merged["services"][name]
            self.assertEqual(svc["secrets"], ["django_secret_key"], name)
            self.assertEqual(svc["environment"]["DJANGO_SECRET_KEY_FILE"], "/run/secrets/django_secret_key")
            self.assertIn("DATABASE_URL", svc["environment"])  # the base environment survived
        self.assertEqual(merged["secrets"]["django_secret_key"]["file"], "./secrets/django_secret_key")

    def test_merge_rules(self):
        self.assertEqual(cl.merge({"a": [1]}, {"a": [1, 2]}), {"a": [1, 2]})
        self.assertEqual(cl.merge({"command": ["a"]}, {"command": ["b"]}), {"command": ["b"]})
        self.assertEqual(cl.merge({"e": {"x": 1}}, {"e": {"y": 2}}), {"e": {"x": 1, "y": 2}})


def doc(**services):
    return {"services": services}


class SingleFileRuleTests(unittest.TestCase):
    def test_cl001_unpinned_images(self):
        self.assertIn("CL001", rules(cl.lint_file("f", doc(a={"image": "redis"}))))
        self.assertIn("CL001", rules(cl.lint_file("f", doc(a={"image": "redis:latest"}))))
        self.assertNotIn("CL001", rules(cl.lint_file("f", doc(a={"image": "redis:8"}))))
        self.assertNotIn("CL001", rules(cl.lint_file("f", doc(a={"image": "${IMG}:${TAG:-dev}"}))))
        self.assertNotIn("CL001", rules(cl.lint_file("f", doc(a={"image": "localhost:5000/app:1"}))))

    def test_cl002_ports_must_bind_to_localhost(self):
        self.assertIn("CL002", rules(cl.lint_file("f", doc(db={"ports": ["5432:5432"]}))))
        self.assertIn("CL002", rules(cl.lint_file("f", doc(db={"ports": ["0.0.0.0:5432:5432"]}))))
        self.assertNotIn("CL002", rules(cl.lint_file("f", doc(db={"ports": ["127.0.0.1:5432:5432"]}))))
        self.assertIn("CL002", rules(cl.lint_file("f", doc(db={"ports": [{"published": 5432, "target": 5432}]}))))

    def test_cl005_literal_secrets(self):
        bad = doc(a={"environment": {"DJANGO_SECRET_KEY": "hunter2"}})
        self.assertIn("CL005", rules(cl.lint_file("f", bad)))
        bad_list = doc(a={"environment": ["API_TOKEN=abc"]})
        self.assertIn("CL005", rules(cl.lint_file("f", bad_list)))
        ok = doc(a={"environment": {"DJANGO_SECRET_KEY": "${DJANGO_SECRET_KEY:-}",
                                    "DJANGO_SECRET_KEY_FILE": "/run/secrets/x"}})
        self.assertEqual(cl.lint_file("f", ok), [])

    def test_cl007_old_postgres_data_path(self):
        bad = doc(db={"volumes": ["pgdata:/var/lib/postgresql/data"]})
        self.assertIn("CL007", rules(cl.lint_file("f", bad)))

    def test_cl009_celery_beat_replicas(self):
        bad = doc(**{"celery-beat": {"deploy": {"replicas": 2}}})
        self.assertIn("CL009", rules(cl.lint_file("f", bad)))

    def test_cl011_debug_outside_dev(self):
        bad = doc(a={"environment": {"DJANGO_DEBUG": "true"}})
        self.assertIn("CL011", rules(cl.lint_file("compose.yaml", bad)))
        self.assertNotIn("CL011", rules(cl.lint_file("compose.dev.yaml", bad)))

    def test_cl012_version_key(self):
        self.assertIn("CL012", rules(cl.lint_file("f", {"version": "3.8", "services": {}})))

    def test_cl013_unescaped_dollar_in_healthcheck(self):
        bad = doc(a={"healthcheck": {"test": ["CMD-SHELL", "pg_isready -U $POSTGRES_USER"]}})
        self.assertIn("CL013", rules(cl.lint_file("f", bad)))
        ok = doc(a={"healthcheck": {"test": ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER"]}})
        self.assertNotIn("CL013", rules(cl.lint_file("f", ok)))
        ok2 = doc(a={"healthcheck": {"test": ["CMD-SHELL", "echo ${X:-1}"]}})
        self.assertNotIn("CL013", rules(cl.lint_file("f", ok2)))


class MergedRuleTests(unittest.TestCase):
    def prod_with(self, mutate):
        merged = copy.deepcopy(cl.merge_files(BASE, PROD))
        mutate(merged["services"])
        return rules(cl.lint_merged("t", merged, True))

    def test_real_merges_are_clean(self):
        self.assertEqual(cl.lint_merged("dev", cl.merge_files(BASE, DEV), False), [])
        self.assertEqual(cl.lint_merged("prod", cl.merge_files(BASE, PROD), True), [])
        self.assertEqual(cl.lint_merged("prod+s", cl.merge_files(BASE, PROD, SECRETS), True), [])

    def test_the_command_line_also_checks_the_base_file_alone(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "compose.yaml").write_text(
                "services:\n  a:\n    image: x:1\n    depends_on:\n      - ghost\n")
            (Path(tmp) / ".env.example").write_text("COMPOSE_FILE=compose.yaml\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cl.main([tmp]), 1)
            self.assertIn("CL004", out.getvalue())

    def test_cl004_unknown_dependency(self):
        self.assertIn("CL004", self.prod_with(lambda s: s["backend"]["depends_on"].update({"ghost": {"condition": "service_started"}})))

    def test_cl004_waiting_for_health_without_a_health_check(self):
        self.assertIn("CL004", self.prod_with(lambda s: s["redis"].pop("healthcheck")))
        self.assertIn("CL004", self.prod_with(lambda s: s["redis"].update({"healthcheck": {"disable": True}})))

    def test_cl004_dependency_without_a_condition(self):
        self.assertIn("CL004", self.prod_with(lambda s: s["backend"]["depends_on"].update({"db": {}})))

    def test_cl003_restart_policies(self):
        self.assertIn("CL003", self.prod_with(lambda s: s["backend"].pop("restart")))
        self.assertIn("CL003", self.prod_with(lambda s: s["migrate"].update({"restart": "unless-stopped"})))

    def test_cl008_hardening_and_log_rotation(self):
        self.assertIn("CL008", self.prod_with(lambda s: s["backend"].pop("cap_drop")))
        self.assertIn("CL008", self.prod_with(lambda s: s["db"].pop("logging")))
        self.assertIn("CL008", self.prod_with(lambda s: s["frontend"].pop("security_opt")))

    def test_cl002_production_ports(self):
        self.assertIn("CL002", self.prod_with(lambda s: s["db"].update({"ports": ["127.0.0.1:5432:5432"]})))


class EnvExampleTests(unittest.TestCase):
    def test_variables_without_defaults_are_found(self):
        found = cl.variables("a ${X:?msg} ${Y:-1} ${Z} ${Y:?no}")
        self.assertEqual(found, {"X": False, "Y": False, "Z": False})
        self.assertEqual(cl.variables("${Y:-1}"), {"Y": True})

    def test_real_env_example_covers_the_real_files(self):
        texts = {"compose.yaml": BASE, "compose.prod.yaml": PROD, "compose.dev.yaml": DEV}
        self.assertEqual(cl.lint_env_example(texts, ENV), [])

    def test_missing_variable_is_reported(self):
        trimmed = "\n".join(l for l in ENV.splitlines() if not l.startswith("POSTGRES_PASSWORD="))
        found = cl.lint_env_example({"compose.yaml": BASE}, trimmed)
        self.assertEqual(rules(found), {"CL006"})
        self.assertTrue(all("POSTGRES_PASSWORD" in f.message for f in found))

    def test_compose_file_must_be_set(self):
        trimmed = "\n".join(l for l in ENV.splitlines() if not l.startswith("COMPOSE_FILE="))
        self.assertIn("CL010", rules(cl.lint_env_example({}, trimmed)))

    def test_every_required_variable_has_a_safe_placeholder(self):
        for line in ENV.splitlines():
            if line.startswith("POSTGRES_PASSWORD=") or line.startswith("DJANGO_SECRET_KEY="):
                self.assertIn("change-me", line)


class Missing(Exception):
    pass


def expand_string(text: str, env: dict) -> str:
    """A tiny stand-in for Compose's ${VAR} expansion: ${V}, ${V:-d}, ${V:?msg}, and $$ (escape)."""
    import re

    def one(match):
        if match.group(0) == "$$":
            return "$"
        name, op, arg = match.group(1), match.group(2), match.group(3)
        value = env.get(name, "")
        if op == ":?" and value == "":
            raise Missing(arg or name)
        if op == ":-" and value == "":
            return arg
        return value

    return re.sub(r"\$\$|\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:-|:\?)([^}]*))?\}", one, text)


def expand(text: str, env: dict):
    """Parse the YAML first, then expand every string (as Compose does)."""
    def walk(node):
        if isinstance(node, str):
            return expand_string(node, env)
        if isinstance(node, list):
            return [walk(item) for item in node]
        if isinstance(node, dict):
            return {key: walk(value) for key, value in node.items()}
        return node
    return walk(cl.load(text))


def env_values(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            out[key] = value
    return out


class ExpansionTests(unittest.TestCase):
    def test_the_example_values_produce_a_valid_resolved_file(self):
        resolved = expand(BASE, env_values(ENV))
        env = resolved["services"]["backend"]["environment"]
        self.assertEqual(env["DATABASE_URL"], "postgres://chat:change-me-use-a-long-random-value@db:5432/chat")
        self.assertEqual(env["DJANGO_DEBUG"], "false")
        self.assertEqual(resolved["services"]["backend"]["image"], "ai-chat-backend:dev")
        args = resolved["services"]["frontend"]["build"]["args"]
        self.assertEqual(args["NEXT_PUBLIC_API_URL"], "http://127.0.0.1:8000")

    def test_dollar_dollar_survives_for_the_container_shell(self):
        resolved = expand(BASE, env_values(ENV))
        self.assertEqual(resolved["services"]["db"]["healthcheck"]["test"][1],
                         "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}")
        # and Compose's own variables in the same file ARE expanded
        self.assertEqual(resolved["services"]["db"]["environment"]["POSTGRES_USER"], "chat")

    def test_a_missing_required_value_stops_with_our_message(self):
        values = env_values(ENV)
        values.pop("POSTGRES_PASSWORD")
        with self.assertRaises(Missing) as caught:
            expand(BASE, values)
        self.assertIn("in .env", str(caught.exception))

    def test_production_image_names_and_tags_can_be_set_from_env(self):
        values = env_values(ENV)
        values.update(BACKEND_IMAGE="ghcr.io/me/ai-chat-backend", APP_VERSION="a1b2c3d")
        resolved = expand(BASE, values)
        self.assertEqual(resolved["services"]["celery-worker"]["image"], "ghcr.io/me/ai-chat-backend:a1b2c3d")


class DockerfileAmendmentTests(unittest.TestCase):
    def test_media_directory_is_created_for_the_app_user(self):
        text = read("backend/Dockerfile")
        self.assertIn("mkdir -p /app/media", text)
        self.assertLess(text.index("mkdir -p /app/media"), text.index("USER app"))


if __name__ == "__main__":
    unittest.main()
