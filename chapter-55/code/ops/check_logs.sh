#!/bin/sh
# Check the last 15 minutes of backend logs for attack and error patterns, then tell the
# heartbeat service: success ping when quiet, /fail with the alert text when not.
# Needs LOGALERTS_PING_URL in the environment (see crontab.example).
set -u
cd "$(dirname "$0")/.."
: "${LOGALERTS_PING_URL:?set LOGALERTS_PING_URL}"

OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT

if docker compose logs --no-log-prefix --since 15m backend 2>/dev/null \
     | python3 backend/core/observability/logalerts.py > "$OUT"; then
    curl -fsS -m 10 "$LOGALERTS_PING_URL" > /dev/null
else
    curl -fsS -m 10 --data-binary @"$OUT" "$LOGALERTS_PING_URL/fail" > /dev/null
fi
