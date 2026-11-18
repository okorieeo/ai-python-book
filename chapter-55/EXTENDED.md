# Chapter 55 — Monitoring, Logging and Scaling: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Logs That Answer Questions › Reading logs with jq

`docker compose logs` prefixes each line with the service name. `--no-log-prefix` removes it, and then `jq`, a small command-line JSON tool, turns the logs into answers:

**bash terminal**

```bash
# Everything one request did, across backend and Celery
docker compose logs --no-log-prefix backend celery-worker \
  | jq -c 'select(.request_id == "req_7f3a9c")'
 
# Errors in the last hour
docker compose logs --no-log-prefix --since 1h backend | jq -c 'select(.level == "ERROR")'
 
# The five slowest requests in the last 15 minutes
docker compose logs --no-log-prefix --since 15m backend \
  | jq -c 'select(.event == "http_request") | [.fields.ms, .fields.path, .fields.status]' \
  | sort -t[ -k2 -n -r | head -5
```

Lines that are not JSON (a startup banner, a traceback) make `jq` complain; add `2>/dev/null` or filter with `grep '^{'` first. Docker keeps only what the rotation allows (about 30 MB per service in Chapter 52), so these commands answer questions about **the last hours or days**, not last month. When you need longer memory, you move the logs somewhere else:

| **Option** | **Good for** | **Trade-off** |
|---|---|---|
| `docker compose logs` + `jq` | A solo developer, the first months | Short memory; nothing to install; search is manual |
| **The log viewer in your deployment tool (Dokploy, Chapter 54)** | Quick looks at live logs from a browser | Usually live tailing, not long-term search |
| **A hosted log service (many have a free tier)** | Weeks of searchable history and alerts, no servers to run | Your logs leave the server: scrub them first, and read the provider's retention and region |
| **Self-hosted Loki with Grafana** | Full control, long retention | Another stack to run, patch and back up on your own server |

Start with the first row. Move when you find yourself wishing you could search last Tuesday.


## Health, Readiness and Uptime Monitoring › Setting up the outside monitor

Pick any uptime service; many have a free tier that checks every few minutes (at the time of writing, UptimeRobot's free plan allowed about 50 monitors at 5-minute intervals, but plans change, so look). What matters is what you configure:

| **Monitor** | **URL** | **Pass when** | **Why** |
|---|---|---|---|
| **Website** | `https://app.example.com/` | Status 200 and a word from your page | What users see |
| **API liveness** | `https://api.example.com/healthz/` | Status 200 | The process is answering through the proxy and TLS |
| **API readiness** | `https://api.example.com/readyz/` | Status 200 and the keyword `ok` | PostgreSQL and Redis work |
| **Certificate** | The same hostnames | More than 14 days to expiry | Automatic renewal failed silently |

- **Require two failures in a row** before alerting. One failed check in a thousand is a network blip, not an outage.
- **Send alerts somewhere you actually look**: email plus a push channel (the app's push, Telegram or Slack), not email alone.
- **Pause or mute during planned work.** Chapter 54's zero-downtime deployments should not trigger it, but a server migration will.
- **Do not put secrets in the monitored URL.** Both endpoints are public by design and reveal only `ok` or `unavailable`.

## Heartbeats: Noticing Silence › Watching the scheduler and everything behind it

One tiny periodic task proves a surprising amount. If it reaches the monitor every five minutes, then Celery Beat is alive, Redis is up, a worker is processing tasks, the database settings loaded and the server can reach the internet. If any of them breaks, the pings stop and you hear about it:

**core/tasks.py (add)**

```
import os
 
from celery import shared_task
 
from core.observability.heartbeat import ping
 
 
@shared_task(ignore_result=True)
def heartbeat_beat():
    """Every 5 minutes. If it stops arriving, Beat, Redis, a worker or the network died."""
    ping(os.environ.get("HEARTBEAT_URL_BEAT"))
```

**config/settings.py (add to your Celery Beat schedule)**

```
CELERY_BEAT_SCHEDULE = {
    # ... your existing entries ...
    "heartbeat": {"task": "core.tasks.heartbeat_beat", "schedule": 300.0},
}
```

If Chapter 15 uses `django-celery-beat` with its database scheduler, add the same entry through the admin instead of in settings. Create one check per job in your heartbeat service and give each its own URL:

| **Check** | **Period** | **Grace** | **Sent by** |
|---|---|---|---|
| **Scheduler and workers** | 5 minutes | 3 minutes | `heartbeat_beat` task |
| **Nightly backup** | 1 day | 2 hours | `backup.py` |
| **Log alert checker** | 5 minutes | 5 minutes | `check_logs.sh` |


## Turning Logs into Alerts

Chapter 17 ended its security chapter with a list of things worth alerting on and promised Chapter 55 would build the machinery. This is it. `logalerts.py` reads **one window** of JSON logs, counts the patterns that matter and prints an alert for each threshold that is crossed. It exits with code 1 when there is anything to report, which is what lets cron and a heartbeat service turn it into a notification.

| **Alert** | **Counted from** | **Default threshold per window** | **What it usually means** |
|---|---|---|---|
| `auth_failures` | `login_failed` events plus HTTP 401 | 20 | Password guessing or credential stuffing |
| `probing_by_USER` | HTTP 403 and 404 for one user id | 30 | Someone testing ids that are not theirs (Chapter 17's IDOR) |
| `rate_limited` | HTTP 429 | 50 | A script hitting your limits, or limits that are too tight |
| `server_errors` | HTTP 5xx | 5, or 5% of requests (with at least 50) | A bug, a dead dependency, a bad deploy |
| `slow_requests_p95_ms` | 95th percentile of `ms` (at least 50 requests) | 2000 ms | Slow queries, a slow AI provider, a busy server |
| `webhook_signature_failures` | `webhook_signature_failed` events | 3 | Forged provider events, or a signing secret that changed |

Run it on the last 15 minutes of backend logs. Here it is on a synthetic window containing a burst of rate limiting, one user probing, a few server errors and failed logins (the `backend-1  |` prefix is what `docker compose logs` adds, and the tool copes with it):

**text verified output**

```text
$ python backend/core/observability/logalerts.py < window.log
ALERT auth_failures: 22 (threshold 20). Credential stuffing or password
  guessing? Check the audit trail and rate limits.
ALERT probing_by_mallory: 34 (threshold 30). Many 403/404 for one user:
  someone may be probing for other people's objects.
ALERT rate_limited: 55 (threshold 50). A script is hitting your limits, or
  the limits are too tight for real users.
ALERT server_errors: 6 (threshold 5). 2.2% of 275 requests failed. See
  Sentry for the cause.
$ echo $?
1
```

(Messages are wrapped here for the page; the tool prints one alert per line.) A short shell script runs it on a schedule. It pings the heartbeat service with **success** when there are no alerts and with **/fail plus the alert text** when there are, so a single check both proves the checker ran and carries the message to your phone. The test suite runs this script against stand-ins for `docker` and `curl` and checks both paths:

**ops/check_logs.sh**

```
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
```

**ops/crontab.example (the log alert line)**

```
LOGALERTS_PING_URL=https://hc-ping.com/replace-with-another-uuid
 
*/5 * * * * /srv/ai-chat/ops/check_logs.sh
```

- **Tune it with data.** Run the tool by hand for a week without paging anyone, look at what normal traffic produces, and set each threshold comfortably above it. An alert that fires daily teaches you to ignore alerts.
- **Windows overlap.** Checking every 5 minutes over the last 15 means one incident can alert up to three times. That is a feature while you are learning; widen the interval later.
- **It sees user ids, not network addresses.** Per-IP patterns live in the reverse proxy's access log (Chapter 54), and blocking an address is the proxy's or firewall's job (Chapter 53).
- **The webhook event name is yours.** Use the event your payment webhook handler logs when a signature check fails; change `WEBHOOK_EVENT` at the top of the file if it differs.

## Metrics Without a Metrics Stack

Operations people talk about four **golden signals**: **latency** (how long requests take), **traffic** (how many), **errors** (how many fail) and **saturation** (how full the machine is). You already have the first three from the request log and Sentry. Saturation comes from the server itself, and on one VPS a handful of commands beat a dashboard you never open:

| **Question** | **Command** | **Worry when** |
|---|---|---|
| **Is the disk filling?** | `df -h /` and `docker system df` | Above 80% used |
| **Is memory short?** | `free -m` and `docker stats --no-stream` | Little "available", or a container near its limit |
| **Was something killed for memory?** | `docker inspect -f '{{.State.OOMKilled}}' NAME` | `true` (exit code 137, Chapter 51) |
| **Is the machine busy?** | `uptime` (the load averages) | Load above the number of CPU cores for long periods |
| **Are PostgreSQL connections running out?** | `docker compose exec db psql -U chat -c "select count(*) from pg_stat_activity;"` | Near `max_connections` (100 by default) |
| **Is Redis full?** | `docker compose exec redis redis-cli info memory` | `used_memory_human` growing without end |
| **Is the Celery queue backing up?** | `docker compose exec redis redis-cli llen celery` | Growing steadily, not draining |
| **What is the worker doing?** | `docker compose exec celery-worker celery -A config inspect active` | Tasks stuck for a very long time |

PostgreSQL can also tell you which queries are slow. Ask it to write any statement that takes longer than half a second into its own log, which you read with `docker compose logs db`:

**bash terminal**

```bash
docker compose exec db psql -U chat \
  -c "ALTER SYSTEM SET log_min_duration_statement = 500;" \
  -c "SELECT pg_reload_conf();"
```

When you outgrow commands, add a tool, one at a time and only for a question you cannot answer today: your VPS provider's built-in graphs and alerts for CPU, memory and disk (switch on the disk alert first), Dokploy's server and container graphs (Chapter 54), and later a self-hosted dashboard such as Netdata or Prometheus with Grafana. Each of those is one more thing to run, patch and back up, so earn it.


## Backups and Disaster Recovery › Offsite copies and retention

- **3-2-1:** three copies of the data (live plus two backups), on two kinds of storage, with one offsite. The live database, the local encrypted dumps and the offsite bucket meet it.
- **Use a storage account for backups only,** with credentials that can write but ideally not delete. Turn on **versioning or object lock** (immutability) in the bucket: that is what saves you from ransomware, from a bug, and from your own mistaken command.
- **Retention in the script is local only.** Set an expiry (lifecycle) rule on the bucket as well, so old copies do not accumulate and cost money forever.
- **Backups are personal data too.** A user who deletes their account still exists in backups until those expire. Keep retention short, and say so in your privacy policy (Chapter 34).
The retention function is pure and carefully tested: it keeps the newest backup of each of the last N days, ISO weeks and months; never deletes the newest backup of all, however old it is; and never touches a file whose name it does not recognise (so a stray `notes.txt` in the folder is safe).

Run it every night from the deployment user's crontab (Chapter 53), with its settings in the crontab's environment lines:

**ops/crontab.example**

```
# Install with:  crontab -e   (as the deployment user from Chapter 53, not root)
# Every job pings an outside monitor, so SILENCE (cron stopped, server dead) alarms.
BACKUP_AGE_RECIPIENT=age1replacewithyourpublickey
BACKUP_HEARTBEAT_URL=https://hc-ping.com/replace-with-your-uuid
 
# 03:15 every day: back up PostgreSQL
15 3 * * * cd /srv/ai-chat && python3 ops/backup.py >> /var/log/ai-chat-backup.log 2>&1
 
LOGALERTS_PING_URL=https://hc-ping.com/replace-with-another-uuid
 
# every 5 minutes: look for attack and error patterns in the last 15 minutes of logs.
# Quiet -> success ping; alerts -> /fail ping carrying the alert text (see check_logs.sh).
*/5 * * * * /srv/ai-chat/ops/check_logs.sh
```

Chapter 54's Dokploy can also schedule database backups to S3-compatible storage. That is a fine choice; whichever tool runs your backups, hold it to the same five questions: **Is it encrypted? Is it offsite? Is it checked? Will a missed run alert me? Have I restored it?**


## Backups and Disaster Recovery › The restore drill

Until you have restored a backup, you have a file and a hope. A drill takes under an hour and answers the questions that matter during a real disaster: can you decrypt it, does it restore, is the data complete, and **how long does it take** (your real RTO). Do it on a scratch copy of the stack, with a different project name so it cannot touch production data:

**bash terminal**

```bash
# 1. Fetch the newest backup and decrypt it (on the machine that holds the private key)
rclone copyto b2:my-bucket/ai-chat/chat-20261110-031500.dump.age .
age -d -i ai-chat-backup.key chat-20261110-031500.dump.age > restore.dump
 
# 2. Start ONLY a scratch database, in its own project
docker compose -p ai-chat-drill -f compose.yaml up -d db
 
# 3. Restore into it (-T: no terminal, the dump comes in on standard input)
docker compose -p ai-chat-drill exec -T db sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error' \
  < restore.dump
 
# 4. Check the data, then compare the count with production
docker compose -p ai-chat-drill exec db psql -U chat -d chat \
  -c "select count(*) from auth_user;"
 
# 5. Throw the scratch project away (here -v IS what you want)
docker compose -p ai-chat-drill down -v
rm restore.dump
```

**Check:** the restore finishes without errors, the row count matches production (to within what changed since the backup), and you wrote down how long steps 1 to 4 took. That number is your measured RTO for the data; add the time to build a server.

The `-p ai-chat-drill` flag overrides the project name in `compose.yaml`, which gives the drill its own volume, separate from the real `ai-chat_pgdata`. Delete `restore.dump` when you finish: it is an unencrypted copy of everything.


## Backups and Disaster Recovery › When things go wrong: a one-page runbook

During an outage you will be stressed and the commands you need are not in your head. Write the answers down **now**, in `docs/runbook.md` in the repository, and keep a copy where you can reach it if the server (and your Git host login) are unavailable:

| **What happened** | **First response** | **Detail lives in** |
|---|---|---|
| **A container keeps crashing** | `docker compose ps -a`, `logs`, exit code; Sentry for the stack trace | Chapter 51, 55.2 |
| **A bad deploy** | Roll back to the previous image in Dokploy | Chapter 54 |
| **Disk full** | `docker system df`, prune images and build cache, check log rotation, grow the disk | Chapter 52, 55.7 |
| **Data deleted or damaged** | Restore the newest good backup into a **scratch** database, copy back what is missing | 55.8 |
| **The server is gone** | New VPS (Chapter 53), Dokploy (Chapter 54), deploy from Git, secrets from the password manager, restore the database, move DNS | 55.8, Chapters 53 and 54 |
| **A secret leaked** | Rotate it, revoke the provider's key, redeploy, read the audit trail | Chapter 17 |
| Someone ran `down -v` | Restore from backup. This is the day the drill pays for itself | 55.8 |
| **Your hosting provider has an outage** | Wait, and tell your users; a single server has no fail-over | 55.9 |


## Scaling: Measure First › Before you add a second app server

Running several copies of the backend is the biggest jump on the ladder, because it only works if nothing important lives inside one container. The checklist:

- **Stateless app.** Sessions in the database or Redis (or signed cookies), never in a container's memory.
- **Shared files.** Uploaded media on object storage, not in a container's local volume (Chapter 16), or every replica sees different files.
- **WebSockets through Redis.** Chapter 14's Redis channel layer already lets any replica reach any connected user; an in-memory layer would break at the second replica.
- **One Beat, one migration job.** Chapter 52's rules do not change: scale workers freely, never the scheduler or the migrate job.
- **A load balancer in front.** The reverse proxy (Chapter 54) must spread requests over replicas and stop sending to unhealthy ones.
- **Enough database.** More app servers means more connections: pool them first (above) and watch `pg_stat_activity`.
One server with a bigger plan carries a surprising amount of traffic. Many successful products never leave steps 2 to 4 of the ladder. A multi-server setup is a project of its own and is outside this book; if you reach step 6, you will have the measurements to justify it.


## Scaling: Measure First › Load testing, carefully

To find your limits, test a **staging copy** with a tool such as k6 or Locust, never production, and never anyone else's service. Two cautions specific to an AI app: replace the AI provider with a **fake** that returns canned text after a short delay (otherwise the test costs real money and measures the provider's rate limits, not your server), and keep Chapter 17's rate limits switched **on** for realistic behaviour while exempting your test user. Watch `docker stats`, the readiness check and the Celery queue while the load climbs; the first resource to saturate is your bottleneck.


## Alerts That Deserve to Wake You

The tools above can produce a great many alerts. Most should not interrupt your evening. Give each alert one of three levels, an owner (you) and a **first action**, and write them down:

| **Alert** | **Source** | **Level** | **First action** |
|---|---|---|---|
| **Site down (two failures in a row)** | Uptime monitor | **Page** (push) | `docker compose ps -a`, logs, roll back the last deploy |
| **Readiness failing** | Uptime monitor | **Page** | Is PostgreSQL or Redis down? Disk full? |
| **Backup did not run, or failed** | Heartbeat | Email now; page if two days in a row | Run `backup.py` by hand; check disk and keys |
| **Scheduler or workers silent** | Heartbeat | Email | `docker compose restart celery-beat celery-worker` |
| **New or regressed error** | Sentry | Email | Triage within the working day |
| **Error spike** | Sentry, `logalerts.py` | Email, page if the site is affected | Read the first stack trace; consider a rollback |
| **Many failed logins or probing** | `logalerts.py` | Email, review same day | Read the audit trail (Chapter 17); tighten limits |
| **Disk above 80%** | Provider alert or cron | Email | Prune and rotate; plan a bigger disk |
| **Certificate expires within 14 days** | Uptime monitor | Email | Check the proxy's renewal (Chapter 54) |
| **AI spend over budget or spiking** | `costguard.py`, provider console | Email, page on a large spike | Find the user or loop; use the kill switch if needed |

- **Three levels only:** page (the product is down or data is at risk), email (act today), dashboard (look when you can).
- **Delete or retune any alert that fired and needed no action.** Do this in the monthly review.
- **Make paging reachable but quiet.** Push notifications for the page level, and let email wait for morning. Being reliably reachable beats being constantly interrupted.
- **Test your alerts**. An alert path you have never triggered is a belief, not a fact.

## Checking It All Automatically

As in Chapters 51 and 52, the code in this chapter ships with tests, and they matter more here because this code is what you rely on when something is already wrong. There are 79 tests that need no Docker, Django, Sentry or network access:

- **Readiness (7 tests):** a hung check cannot hang the endpoint, checks run in parallel, the public answer reveals nothing, failure details never include a connection string, and the database connection is closed after both passing and failing checks.
- **Sentry scrubbing (12 tests):** body, cookies, query string and sensitive headers removed; user reduced to an id; chat content and credentials masked while token counters survive; and nothing sensitive remains **anywhere** in a deliberately full event. One test runs Chapter 17's real redaction module.
- **Heartbeats (8 tests)** against a real local web server, including that a dead monitor changes nothing and that the URL is never logged.
- **Request log and log alerts (19 tests):** path normalisation, the exact fields Chapter 17's formatter expects, health paths skipped, each alert's threshold, an end-to-end line from record to alert.
- **Cost guard (9 tests):** per-million pricing, unknown models, month boundaries, spike and projection alerts, and the command line.
- **Backups (24 tests):** command construction; the happy path and its exact order; **each of four failures** (dump, verify, encrypt, upload) stops the chain, cleans up and sends `/fail`; permissions of `0600` and `0700`; refusing an offsite copy without encryption; pruning only after success; the retention policy across year boundaries; and the shell script that reports log alerts, run with stand-ins for `docker` and `curl`.
Beyond the tests passing, I broke the code on purpose five ways (sending pings over plain HTTP by default, switching Sentry's personal data setting on, keeping frame variables, forgetting to protect the newest backup, and leaking details through the public readiness page), and the suite failed every time. And, as the verification box said, the tests found two real defects while the chapter was being written. That is the argument for testing the unglamorous scripts: **they fail in the moments you can least afford it.**

Add the suites to the workflow from Chapters 51 and 52. The core tests import only `core.observability`, so they run from the `backend` folder without a database:

**.github/workflows/docker-policy.yml (add these steps)**

```
      - run: python -m unittest core.test_observability
        working-directory: backend
      - run: python -m unittest discover -s ops
```

What the tests cannot check is the real services: whether your Sentry project, your monitor and your bucket are configured correctly. That is what the hands-on steps below, and your restore drill, are for.
