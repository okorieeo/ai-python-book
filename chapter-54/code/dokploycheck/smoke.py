"""Post-deploy smoke test: does the LIVE site behave the way the deployment is supposed to?

    python -m dokploycheck.smoke --app https://app.example.com --api https://api.example.com
    python -m dokploycheck.smoke --app ... --api ... --wait 600     # retry until the new version answers

Checks: HTTP redirects to HTTPS, the readiness endpoint, and the security headers set in Chapter 17.
"""
import argparse
import http.client
import json
import sys
import time
import urllib.parse

from .findings import Finding, FAIL, PASS, WARN, worst_status

REQUIRED_HEADERS = {
    "strict-transport-security": "HSTS: browsers refuse to go back to HTTP",
    "x-content-type-options": "stops MIME sniffing",
}


def _request(url: str, method="GET", timeout=8.0):
    """One request, no redirects followed. Returns (status, headers dict lower-case, body bytes)."""
    u = urllib.parse.urlsplit(url)
    cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    conn = cls(u.hostname, u.port, timeout=timeout)
    try:
        conn.request(method, (u.path or "/") + (f"?{u.query}" if u.query else ""), headers={"User-Agent": "dokploycheck-smoke"})
        resp = conn.getresponse()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read(65536)
    finally:
        conn.close()


def check_https_redirect(host_url: str) -> Finding:
    u = urllib.parse.urlsplit(host_url)
    http_url = f"http://{u.netloc}/"
    try:
        status, headers, _ = _request(http_url)
    except OSError as exc:
        return Finding(f"redirect {u.netloc}", FAIL, f"cannot reach {http_url}: {exc} (is port 80 open?)")
    location = headers.get("location", "")
    if status in (301, 302, 307, 308) and location.startswith("https://"):
        note = "" if status in (301, 308) else f" (status {status} is temporary; 301 or 308 is better)"
        return Finding(f"redirect {u.netloc}", PASS if not note else WARN, f"http redirects to {location}{note}")
    return Finding(f"redirect {u.netloc}", FAIL, f"http answered {status} without redirecting to https: add the redirect (section 54.10)")


def check_ready(base_url: str, path="/health/ready") -> Finding:
    name = f"ready {urllib.parse.urlsplit(base_url).netloc}"
    try:
        status, _, body = _request(base_url.rstrip("/") + path)
    except OSError as exc:
        return Finding(name, FAIL, f"cannot connect: {exc}")
    if status == 200:
        return Finding(name, PASS, "200 OK")
    try:
        failing = json.loads(body).get("failing", [])
    except ValueError:
        failing = []
    return Finding(name, FAIL, f"status {status}" + (f", failing: {', '.join(failing)}" if failing else ""))


def check_headers(url: str) -> list:
    name = urllib.parse.urlsplit(url).netloc
    try:
        _, headers, _ = _request(url)
    except OSError as exc:
        return [Finding(f"headers {name}", FAIL, f"cannot connect: {exc}")]
    out = []
    for header, why in REQUIRED_HEADERS.items():
        if header in headers:
            out.append(Finding(f"header {header} {name}", PASS, "present"))
        else:
            out.append(Finding(f"header {header} {name}", WARN, f"missing ({why})"))
    return out


def run(app: str, api: str) -> list:
    findings = []
    for base in (app, api):
        findings.append(check_https_redirect(base))
    findings.append(check_ready(api))
    findings += check_headers(app)
    findings += check_headers(api)
    return findings


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="dokploycheck.smoke")
    p.add_argument("--app", required=True, help="web app base URL, e.g. https://app.example.com")
    p.add_argument("--api", required=True, help="API base URL, e.g. https://api.example.com")
    p.add_argument("--wait", type=int, default=0, help="keep retrying for up to N seconds until there are no failures")
    args = p.parse_args(argv)

    deadline = time.time() + args.wait
    while True:
        findings = run(args.app, args.api)
        if worst_status(findings) != FAIL or time.time() >= deadline:
            break
        time.sleep(10)
    for f in findings:
        print(f.line())
    return 1 if worst_status(findings) == FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
