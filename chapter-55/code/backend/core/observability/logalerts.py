"""Turn the JSON logs into the alerts promised by Chapter 17's table.

    docker compose logs --no-log-prefix --since 15m backend | python backend/core/observability/logalerts.py

Reads one window of logs, counts what matters, prints an alert per breached threshold and
exits 1 if there are any (so cron plus a heartbeat/notifier can page you). Standard library only.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass

DEFAULTS = {
    "auth_failures": 20,        # login_failed events plus HTTP 401, per window
    "probing_per_user": 30,     # 403 + 404 responses to ONE user (IDOR hunting)
    "rate_limited": 50,         # HTTP 429
    "server_errors": 5,         # HTTP 5xx, absolute count
    "server_error_ratio": 0.05, # ... or this share of all requests
    "min_requests": 50,         # below this many requests, ratios and p95 are not judged
    "slow_p95_ms": 2000,
    "webhook_failures": 3,      # use the event name your payment webhook code logs
}
WEBHOOK_EVENT = "webhook_signature_failed"


@dataclass(frozen=True)
class Alert:
    name: str
    value: float
    threshold: float
    hint: str

    def __str__(self) -> str:
        return f"ALERT {self.name}: {self.value:g} (threshold {self.threshold:g}). {self.hint}"


def parse_lines(lines) -> list[dict]:
    """Parse JSON log lines; tolerate a 'service-1  | ' prefix and skip anything that is not JSON."""
    entries = []
    for line in lines:
        start = line.find("{")
        if start < 0:
            continue
        try:
            entry = json.loads(line[start:])
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def _requests(entries):
    for e in entries:
        fields = e.get("fields")
        if e.get("event") == "http_request" and isinstance(fields, dict) and isinstance(fields.get("status"), int):
            yield fields


def evaluate(entries: list[dict], limits: dict | None = None) -> list[Alert]:
    t = {**DEFAULTS, **(limits or {})}
    alerts: list[Alert] = []
    requests = list(_requests(entries))
    statuses = Counter(r["status"] for r in requests)

    failed_logins = sum(1 for e in entries if e.get("event") == "login_failed")
    auth = failed_logins + statuses[401]
    if auth >= t["auth_failures"]:
        alerts.append(Alert("auth_failures", auth, t["auth_failures"],
                            "Credential stuffing or password guessing? Check the audit trail and rate limits."))

    probes = Counter(r.get("user_id") or "anonymous" for r in requests if r["status"] in (403, 404))
    for user, count in probes.items():
        if count >= t["probing_per_user"]:
            alerts.append(Alert(f"probing_by_{user}", count, t["probing_per_user"],
                                "Many 403/404 for one user: someone may be probing for other people's objects."))

    if statuses[429] >= t["rate_limited"]:
        alerts.append(Alert("rate_limited", statuses[429], t["rate_limited"],
                            "A script is hitting your limits, or the limits are too tight for real users."))

    errors = sum(n for s, n in statuses.items() if s >= 500)
    total = len(requests)
    ratio = errors / total if total else 0.0
    if errors >= t["server_errors"] or (total >= t["min_requests"] and ratio >= t["server_error_ratio"]):
        alerts.append(Alert("server_errors", errors, t["server_errors"],
                            f"{ratio:.1%} of {total} requests failed. See Sentry for the cause."))

    if total >= t["min_requests"]:
        times = sorted(r["ms"] for r in requests if isinstance(r.get("ms"), (int, float)))
        if times:
            p95 = times[min(len(times) - 1, int(0.95 * len(times)))]
            if p95 >= t["slow_p95_ms"]:
                alerts.append(Alert("slow_requests_p95_ms", p95, t["slow_p95_ms"],
                                    "Look at slow queries, the AI provider's latency, and server load."))

    hooks = sum(1 for e in entries if e.get("event") == WEBHOOK_EVENT)
    if hooks >= t["webhook_failures"]:
        alerts.append(Alert("webhook_signature_failures", hooks, t["webhook_failures"],
                            "Someone may be forging provider events, or a signing secret changed."))
    return alerts


def main(stdin=None, out=None) -> int:
    stdin = stdin or sys.stdin
    out = out or sys.stdout
    alerts = evaluate(parse_lines(stdin))
    for alert in alerts:
        print(alert, file=out)
    if not alerts:
        print("OK no alerts in this window", file=out)
    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
