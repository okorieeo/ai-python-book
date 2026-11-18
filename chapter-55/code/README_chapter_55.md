# Chapter 55 code: Monitoring, Logging and Scaling

Unzip into the root of the AI Chat project. Everything here is NEW; no existing file is replaced.

| File | Purpose |
|---|---|
| `backend/core/observability/readiness.py` | Readiness checks (database, Redis, queue depth) |
| `backend/core/observability/sentry_scrub.py` | Sentry setup that keeps chat text, cookies and keys out of reports |
| `backend/core/observability/heartbeat.py` | Dead-man's-switch pings (Healthchecks.io style) |
| `backend/core/observability/request_log.py` | One JSON log line per request (middleware) |
| `backend/core/observability/logalerts.py` | Turns a window of JSON logs into alerts (Chapter 17's table) |
| `backend/core/observability/costguard.py` | AI spend: daily budget, month projection, spike and unknown-model alerts |
| `backend/core/test_observability.py` | 55 tests for the modules above |
| `ops/backup.py`, `ops/retention.py` | PostgreSQL backup: dump, check, encrypt, offsite, prune, heartbeat |
| `ops/check_logs.sh`, `ops/crontab.example` | Scheduling the log alerts and the backup |
| `ops/prices.example.json` | EXAMPLE prices only; copy to prices.json and fill in your provider's real prices |
| `ops/test_ops.py` | 24 tests for the backup, retention and log-check scripts |

Run the tests (Python 3.12+, standard library only; no Docker, Django or Sentry needed):

    cd backend && python -m unittest core.test_observability && cd ..
    python3 -m unittest discover -s ops

The tests use your project's existing `core` package (and, for one test, Chapter 17's
`core.security.redaction`). Do not overwrite your `core/__init__.py`.

Docker, Django, Sentry, `age`, `rclone` and the uptime and heartbeat services were not
available where this was written, so only what the tests cover was run. The chapter's
section 55.13 is the first real run against real services.
