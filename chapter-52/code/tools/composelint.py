"""A small policy checker for the Compose files in Chapter 52.

It reads YAML only (needs PyYAML: pip install pyyaml). It does not run Docker and it does
not expand ${VARIABLES}. "Merged" views use a SIMPLIFIED version of Compose's merge rules
(maps merge, lists append, command/entrypoint/test replace). Always confirm the real result
with: docker compose config

    python tools/composelint.py            # checks the files in the current folder
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REPLACE_KEYS = {"command", "entrypoint", "test"}
SECRET_NAME = re.compile(r"(SECRET|PASSWORD|PASSWD|TOKEN|API_?KEY|PRIVATE_?KEY)", re.IGNORECASE)
VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:?[-?+][^}]*)?\}")
UNESCAPED_DOLLAR = re.compile(r"(?<!\$)\$(?![\${(])[A-Za-z_]")
ONE_SHOT = {"migrate"}
APP_SERVICES = {"backend", "celery-worker", "celery-beat", "channels-worker", "frontend", "migrate"}
DATA_SERVICES = {"db", "redis"}


@dataclass(frozen=True)
class Finding:
    rule: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule} [{self.where}]: {self.message}"


def load(text: str) -> dict:
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


def merge(base, extra):
    """Simplified Compose merge of two loaded files."""
    if isinstance(base, dict) and isinstance(extra, dict):
        out = dict(base)
        for key, value in extra.items():
            out[key] = value if key in REPLACE_KEYS or key not in base else merge(base[key], value)
        return out
    if isinstance(base, list) and isinstance(extra, list):
        return base + [item for item in extra if item not in base]
    return extra


def merge_files(*texts: str) -> dict:
    result: dict = {}
    for text in texts:
        result = merge(result, load(text))
    return result


def _services(doc: dict) -> dict:
    return doc.get("services") or {}


def _env_map(service: dict) -> dict:
    env = service.get("environment") or {}
    if isinstance(env, list):
        return dict(item.split("=", 1) if "=" in item else (item, "") for item in env)
    return env


def _port_text(port) -> str:
    return str(port.get("published", "")) if isinstance(port, dict) else str(port)


# ------------------------------------------------------------------ rules for one file

def lint_file(name: str, doc: dict) -> list[Finding]:
    found: list[Finding] = []
    if "version" in doc:
        found.append(Finding("CL012", name, "Top-level 'version:' is obsolete; remove it."))
    for sname, svc in _services(doc).items():
        where = f"{name}:{sname}"
        image = svc.get("image")
        if isinstance(image, str) and not image.startswith("$"):
            tail = image.rsplit("/", 1)[-1]
            if ":" not in tail:
                found.append(Finding("CL001", where, f"Image {image!r} has no tag. Pin a version."))
            elif tail.endswith(":latest"):
                found.append(Finding("CL001", where, f"Image {image!r} uses 'latest'. Pin a version."))
        for port in svc.get("ports") or []:
            text = _port_text(port)
            if not (text.startswith("127.0.0.1:") or text.startswith("[::1]:")):
                found.append(Finding("CL002", where, f"Port {text!r} is not bound to 127.0.0.1."))
        env = _env_map(svc)
        for key, value in env.items():
            if str(value).strip().lower() == "true" and key == "DJANGO_DEBUG" and not name.endswith("dev.yaml"):
                found.append(Finding("CL011", where, "DJANGO_DEBUG is true outside the dev overlay."))
            if SECRET_NAME.search(key) and not key.endswith("_FILE"):
                text = str(value)
                if text and not text.startswith("${"):
                    found.append(Finding("CL005", where,
                        f"{key} has a literal value. Use ${{{key}}} from .env, or a secret file."))
        check = svc.get("healthcheck") or {}
        tests = check.get("test")
        tests = [tests] if isinstance(tests, str) else (tests or [])
        for item in tests:
            if isinstance(item, str) and UNESCAPED_DOLLAR.search(item):
                found.append(Finding("CL013", where,
                    "Healthcheck uses $NAME unescaped. Compose expands it first; write $$NAME."))
        if svc.get("deploy", {}).get("replicas", 1) not in (1, "1") and sname == "celery-beat":
            found.append(Finding("CL009", where, "Celery Beat must run as exactly one instance."))
        if sname == "db":
            for vol in svc.get("volumes") or []:
                text = vol if isinstance(vol, str) else vol.get("target", "")
                if text.endswith("/var/lib/postgresql/data") or ":/var/lib/postgresql/data" in text:
                    found.append(Finding("CL007", where,
                        "PostgreSQL 18+ keeps data below /var/lib/postgresql. Mount the volume there."))
    return found


# ------------------------------------------------------------------ rules for a merged result

def lint_merged(label: str, doc: dict, production: bool) -> list[Finding]:
    found: list[Finding] = []
    services = _services(doc)
    for sname, svc in services.items():
        where = f"{label}:{sname}"
        depends = svc.get("depends_on") or {}
        entries = depends.items() if isinstance(depends, dict) else [(d, {}) for d in depends]
        for target, spec in entries:
            if target not in services:
                found.append(Finding("CL004", where, f"depends_on names unknown service {target!r}."))
                continue
            condition = (spec or {}).get("condition") if isinstance(spec, dict) else None
            if condition == "service_healthy":
                health = services[target].get("healthcheck") or {}
                if not health.get("test") or health.get("disable"):
                    found.append(Finding("CL004", where,
                        f"waits for {target!r} to be healthy, but {target!r} has no health check."))
            if condition is None and not isinstance(depends, list):
                found.append(Finding("CL004", where, f"depends_on {target!r} has no condition."))
        if production:
            if sname in ONE_SHOT:
                if svc.get("restart") != "no":
                    found.append(Finding("CL003", where, "One-shot job must have restart: \"no\"."))
            elif svc.get("restart") not in ("unless-stopped", "always", "on-failure"):
                found.append(Finding("CL003", where, "Long-running service has no restart policy."))
            logging = (svc.get("logging") or {}).get("options") or {}
            if "max-size" not in logging:
                found.append(Finding("CL008", where, "No log rotation (logging.options.max-size)."))
            if "no-new-privileges:true" not in (svc.get("security_opt") or []):
                found.append(Finding("CL008", where, "Missing security_opt: no-new-privileges:true."))
            if sname in APP_SERVICES and "ALL" not in (svc.get("cap_drop") or []):
                found.append(Finding("CL008", where, "App container should drop all capabilities (cap_drop: ALL)."))
            if svc.get("ports"):
                found.append(Finding("CL002", where, "Production publishes no ports; the proxy uses the network."))
            if sname in DATA_SERVICES and sname in ("db", "redis") and svc.get("ports"):
                found.append(Finding("CL002", where, "Never publish a data store in production."))
    return found


def variables(text: str) -> dict[str, bool]:
    """Map of ${VARIABLE} names to whether they have a default or are optional."""
    result: dict[str, bool] = {}
    for name, modifier in VARIABLE.findall(text):
        has_default = bool(modifier) and modifier.lstrip(":")[0] in "-+"
        result[name] = result.get(name, True) and has_default
    return result


def lint_env_example(compose_texts: dict[str, str], env_text: str) -> list[Finding]:
    found: list[Finding] = []
    declared = {m.group(1) for m in re.finditer(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=", env_text, re.MULTILINE)}
    active = {m.group(1) for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=", env_text, re.MULTILINE)}
    for name, text in compose_texts.items():
        for var, has_default in variables(text).items():
            if not has_default and var not in active:
                found.append(Finding("CL006", name, f"${{{var}}} has no default and is missing from .env.example."))
    if "COMPOSE_FILE" not in active:
        found.append(Finding("CL010", ".env.example", "COMPOSE_FILE is not set; plain 'docker compose up' would use the wrong files."))
    return found


# ------------------------------------------------------------------ command line

def main(argv: list[str] | None = None) -> int:
    root = Path(argv[0]) if argv else Path(".")
    names = ["compose.yaml", "compose.dev.yaml", "compose.prod.yaml", "compose.secrets.yaml"]
    texts = {}
    for name in names:
        path = root / name
        if path.exists():
            texts[name] = path.read_text(encoding="utf-8")
    if "compose.yaml" not in texts:
        print("MISSING compose.yaml")
        return 1
    findings: list[Finding] = []
    for name, text in texts.items():
        findings += lint_file(name, load(text))
    findings += lint_merged("base", load(texts["compose.yaml"]), False)
    if "compose.dev.yaml" in texts:
        findings += lint_merged("base+dev", merge_files(texts["compose.yaml"], texts["compose.dev.yaml"]), False)
    if "compose.prod.yaml" in texts:
        prod = [texts["compose.yaml"], texts["compose.prod.yaml"]]
        findings += lint_merged("base+prod", merge_files(*prod), True)
        if "compose.secrets.yaml" in texts:
            findings += lint_merged("base+prod+secrets", merge_files(*prod, texts["compose.secrets.yaml"]), True)
    env = root / ".env.example"
    findings += lint_env_example(texts, env.read_text(encoding="utf-8") if env.exists() else "")
    if findings:
        print("FAIL compose files")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print(f"OK   {', '.join(texts)} and .env.example")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
