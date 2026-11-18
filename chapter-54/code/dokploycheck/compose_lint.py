"""Lint a production docker-compose file for the mistakes that hurt on Dokploy.

Run it before every deploy (and in CI):
    python -m dokploycheck deploy/docker-compose.prod.yml --env-example deploy/.env.production.example
"""
import re

import yaml

from .findings import Finding, PASS, WARN, FAIL

DATA_STORES = ("postgres", "redis", "mysql", "mariadb", "mongo", "elasticsearch", "memcached")
SECRET_RE = re.compile(r"(PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)", re.I)
BROWSER_SECRET_RE = re.compile(r"(SECRET|PASSWORD|PRIVATE|TOKEN)", re.I)
VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:?[-?+][^}]*)?\}")
PLACEHOLDER_RE = re.compile(r"^(|CHANGE_ME.*|.*example.*|\.\.\.|<.*>)$", re.I)


def _env_items(value) -> dict:
    """compose allows environment as a list of KEY=VALUE or as a mapping."""
    if not value:
        return {}
    if isinstance(value, dict):
        return {str(k): "" if v is None else str(v) for k, v in value.items()}
    out = {}
    for item in value:
        key, _, val = str(item).partition("=")
        out[key] = val
    return out


def _refs(obj):
    """Every ${VAR...} reference in a nested structure, as (name, modifier)."""
    if isinstance(obj, str):
        for m in VAR_RE.finditer(obj):
            yield m.group(1), m.group(2) or ""
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _refs(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _refs(v)


def parse_env_example(text: str) -> dict:
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def check_env_example(values: dict) -> list:
    findings = []
    for key, val in sorted(values.items()):
        if not SECRET_RE.search(key) or key.startswith("NEXT_PUBLIC_"):
            continue
        if PLACEHOLDER_RE.match(val) or val.startswith("${"):
            continue
        findings.append(Finding(f"env example {key}", FAIL, "looks like a real secret in a file that is committed to Git: use CHANGE_ME or leave it empty"))
    if not findings:
        findings.append(Finding("env example secrets", PASS, "only placeholders"))
    return findings


def lint_compose(text: str, env_example: dict = None, isolated: bool = False) -> list:
    findings = []
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [Finding("compose yaml", FAIL, f"not valid YAML: {exc}")]
    services = (doc or {}).get("services") or {}
    if not services:
        return [Finding("compose services", FAIL, "no services found")]

    if not isolated:
        net = (doc.get("networks") or {}).get("dokploy-network")
        if isinstance(net, dict) and net.get("external") in (True, "true"):
            findings.append(Finding("compose network", PASS, "dokploy-network is declared external"))
        else:
            findings.append(Finding("compose network", FAIL, "declare 'dokploy-network' with 'external: true' so Traefik and the Dokploy databases can reach your services"))

    for name, svc in services.items():
        svc = svc or {}
        image = str(svc.get("image", ""))
        is_store = any(s in image.lower() or s in name.lower() for s in DATA_STORES)
        one_shot = str(svc.get("restart", "")).lower() in ("no", "false")

        if svc.get("ports"):
            bad = [p for p in svc["ports"] if not str(p).startswith("127.0.0.1:")]
            if bad and is_store:
                findings.append(Finding(f"{name} ports", FAIL, f"data store publishes {bad} to the internet (Docker bypasses UFW): remove 'ports:'"))
            elif bad:
                findings.append(Finding(f"{name} ports", WARN, f"publishes {bad} on the host: with Dokploy domains use 'expose:' and let Traefik route"))
        if image and "${" not in image and (image.endswith(":latest") or ":" not in image.split("/")[-1]):
            findings.append(Finding(f"{name} image", FAIL, f"'{image}' is not pinned to a version: a redeploy can pull a different image"))
        if "container_name" in svc:
            findings.append(Finding(f"{name} container_name", WARN, "a fixed container_name blocks recreate-and-replace deploys and can clash with other projects"))
        if svc.get("privileged"):
            findings.append(Finding(f"{name} privileged", FAIL, "privileged containers can take over the host"))
        for vol in svc.get("volumes") or []:
            v = str(vol if not isinstance(vol, dict) else vol.get("source", ""))
            if "docker.sock" in v:
                findings.append(Finding(f"{name} docker.sock", FAIL, "mounting the Docker socket gives the container control of the server"))
            elif v.startswith("/") and ":" in v:
                findings.append(Finding(f"{name} volume", FAIL, f"absolute host path '{v}' is cleaned up by Dokploy deploys: use a named volume or ../files/"))
            elif v.startswith("./"):
                findings.append(Finding(f"{name} volume", WARN, f"'{v}' points into the repository, which Dokploy re-clones on each deploy: use a named volume or a Dokploy file mount"))
        if not one_shot and "restart" not in svc and not (svc.get("deploy") or {}).get("restart_policy"):
            findings.append(Finding(f"{name} restart", WARN, "no restart policy: the container stays down after a crash or a server reboot (use 'unless-stopped')"))
        if (svc.get("expose") or svc.get("ports")) and not svc.get("healthcheck") and not is_store:
            findings.append(Finding(f"{name} healthcheck", WARN, "a service that receives traffic should have a healthcheck"))
        if not isolated and "dokploy-network" not in (svc.get("networks") or []) and not svc.get("network_mode"):
            findings.append(Finding(f"{name} networks", WARN, "not attached to dokploy-network"))

        env = _env_items(svc.get("environment"))
        build = svc.get("build")
        build_args = _env_items(build.get("args")) if isinstance(build, dict) else {}
        for key, val in {**env, **build_args}.items():
            if key.startswith("NEXT_PUBLIC_"):
                if BROWSER_SECRET_RE.search(key):
                    findings.append(Finding(f"{name} {key}", FAIL, "NEXT_PUBLIC_ values are baked into the JavaScript every visitor downloads: never put a secret there"))
            elif SECRET_RE.search(key) and val and not val.startswith("${"):
                findings.append(Finding(f"{name} {key}", FAIL, "secret written into the compose file: reference it as ${VAR:?message} instead"))

    refs = list(_refs(doc))
    if env_example is not None:
        for var in sorted({v for v, mod in refs if not mod.startswith((":-", "-"))}):
            if var not in env_example:
                findings.append(Finding(f"variable {var}", FAIL, "used in the compose file but not defined in the .env example (a deploy would run without it)"))
    secret_refs = {v for v, mod in refs if SECRET_RE.search(v) and not v.startswith("NEXT_PUBLIC_")}
    with_guard = {v for v, mod in refs if mod.startswith(":?")}
    for var in sorted(secret_refs - with_guard):
        findings.append(Finding(f"variable {var}", WARN, "secret referenced without ':?': a missing value silently becomes empty. Use ${%s:?set it in Dokploy}" % var))

    if not any(f.status in (FAIL, WARN) for f in findings):
        findings.append(Finding("compose", PASS, "no problems found"))
    return findings
