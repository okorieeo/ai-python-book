# Chapter 15 — Background Tasks and Scheduling with Celery: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Setting Up Celery with Redis › The settings

**python  config/settings.py (Celery section)**

```python
# ------------------------------------------------------------------- Celery
from celery.schedules import crontab  # noqa: E402

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

CELERY_BROKER_URL = REDIS_URL                # no result backend: see 15.3
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1        # fair dispatch for long jobs
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {"chat.tasks.ingest_document": {"queue": "ingest"}}
```

| **Setting** | **What it does and why** |
|---|---|
| `CELERY_BROKER_URL` | Where the queue lives. Read from the `REDIS_URL` environment variable, so Docker, staging and production only change an environment variable (Chapter 5) |
| `ACCEPT_CONTENT` / `TASK_SERIALIZER` | **JSON only.** Celery can also pickle arbitrary Python objects, but a pickled message can run code when a worker reads it. If anyone can ever write to your broker, pickle turns that into remote code execution |
| `CELERY_TIMEZONE` | UTC, like every timestamp in the API (Chapter 8). Schedules in section 15.6 are therefore in UTC too |
| `TASK_ACKS_LATE` | Acknowledge a message after the task finishes, not when it starts, so a crashed worker’s job is redelivered (section 15.4) |
| `WORKER_PREFETCH_MULTIPLIER = 1` | By default each worker process grabs several messages ahead of time. With long jobs that means a busy worker hoards tasks while another sits idle. `1` means "take one at a time" |
| `BROKER_CONNECTION_RETRY_ON_STARTUP` | If Redis is not ready yet when the worker boots (common in Docker), keep trying instead of exiting |
| `TASK_DEFAULT_QUEUE` / `TASK_ROUTES` | Everything goes to `default` unless routed. Ingestion is routed to its own `ingest` queue (section 15.5) |

> **Why there is no result backend**
>
> Celery can store each task’s return value in a "result backend" (often Redis) so that code can call `.get()` on it. We leave it out on purpose. In a real test with Redis stopped, `.delay()` with a result backend configured **hung for 19 seconds and then raised a** `RuntimeError`, turning a failed enqueue into a slow `500` response. Without the backend the same call fails in under a second with a clear `OperationalError` that we can catch (section 15.3). And because our status lives in the database, nothing needs the backend anyway.


## Setting Up Celery with Redis › Start a worker

**terminal**

```bash
celery -A config worker -Q default,ingest -l info --concurrency 2 -E
```

`-A config` names the application, `-Q` lists the queues this worker serves, `-l info` sets the log level, `--concurrency 2` runs two worker processes, and `-E` publishes task events so that Flower can watch. The startup banner is a useful checklist. Here is the real one from our project:

**worker banner**

```
 -------------- celery@vm v5.6.3 (recovery)
- ** ---------- [config]
- ** ---------- .> app:         config:0x7f9c7e4b6e70
- ** ---------- .> transport:   redis://localhost:6379/0
- ** ---------- .> results:     disabled://
- *** --- * --- .> concurrency: 2 (prefork)
-- ******* ---- .> task events: ON
 -------------- [queues]
                .> default          exchange=default(direct) key=default
                .> ingest           exchange=ingest(direct) key=ingest

[tasks]
  . chat.tasks.daily_usage_report
  . chat.tasks.fail_stuck_documents
  . chat.tasks.ingest_document
  . chat.tasks.purge_deleted_conversations
  . chat.tasks.purge_idempotency_keys

INFO/MainProcess] Connected to redis://localhost:6379/0
INFO/MainProcess] celery@vm ready.
```

Check three things every time: the **transport** is the Redis you expect, the **queues** are the ones you intended, and every task you wrote appears under **[tasks]**. If a task is missing there, the worker will reject messages for it. Workers do not reload automatically: **restart the worker after changing task code**.


## Retries, Errors and Failure Handling › Giving up gracefully

What happens when the fourth retry fails too? If we did nothing, Celery would mark the task as failed, and the document would stay `processing` forever while the user waits. That is the worst outcome: **silent limbo**. So the task checks `self.request.retries >= self.max_retries` and, on the last attempt, marks the document `failed` with a human-readable error instead of raising again. The user sees `failed` and a reason, and can retry with `reindex`. Two more nets catch what slips through: the stuck-document sweeper of section 15.6, and error tracking with Sentry in Chapter 47.

> **Task state is not business state**
>
> In Flower, the `corrupt.pdf` task shows **SUCCESS**: the function ran to the end and returned `"failed"`. The *document* is what failed. Celery’s task states describe whether the function crashed; your database describes whether the business outcome was good. Always put the second one in the row.


## Scheduled Jobs with Celery Beat › Run it and trigger tasks by hand

**terminal**

```bash
celery -A config beat -l info
```

**output**

```text
celery beat v5.6.3 (recovery) is starting.
LocalTime -> 2026-11-03 01:15:34
Configuration ->
    . broker -> redis://localhost:6379/0
    . loader -> celery.loaders.app.AppLoader
    . scheduler -> celery.beat.PersistentScheduler
    . db -> celerybeat-schedule
    . logfile -> [stderr]@%INFO
    . maxinterval -> 5.00 minutes (300s)
INFO/MainProcess] beat: Starting...
```

Beat remembers when it last ran each job in a small file, `celerybeat-schedule`, in the working directory. Add it to `.gitignore`. To run a task right now, without waiting for the clock, use `celery call`, which publishes the same message Beat would:

**terminal**

```bash
celery -A config call chat.tasks.purge_idempotency_keys
celery -A config call chat.tasks.daily_usage_report
```

**worker log**

```
Task chat.tasks.purge_idempotency_keys[a0c8] received
Task chat.tasks.purge_idempotency_keys[a0c8] succeeded in 0.0017s: 0
Task chat.tasks.daily_usage_report[d40a] received
usage 2026-11-02: 0 users, 0 tokens
Task chat.tasks.daily_usage_report[d40a] succeeded in 0.0070s:
    {'date': '2026-11-02', 'users': 0, 'tokens': 0}
```

> **Schedules in the database**
>
> A schedule written in `settings.py` changes only with a deploy. The package `django-celery-beat` stores schedules in database tables instead, so an administrator can add, disable or edit a job in the Django admin (Chapter 22) without redeploying. Start with `settings.py`; switch when you want to change schedules at runtime.


## Monitoring with Flower

A queue you cannot see is a queue you cannot trust. **Flower** is a small web application that connects to the broker and shows workers, tasks, retries, runtimes and queue lengths in real time. Workers must be started with `-E` so they publish the events Flower reads.

**terminal**

```bash
celery -A config flower --port=5555 --basic-auth=admin:change-me
```

Open `http://localhost:5555`. The tabs worth knowing:

| **Tab** | **What you learn from it** |
|---|---|
| Dashboard | Which workers are online, how many tasks each has processed, succeeded and failed, right now |
| Tasks | Every task with its state, arguments, start time, runtime and number of retries; searchable and filterable |
| Workers | One worker’s queues, concurrency, registered tasks, and settings; buttons to change the pool size or shut it down |
| Broker | Messages waiting in each queue: the number that tells you the system is falling behind |

Flower also has an HTTP API, handy for scripts and alerts. This is real output from our project after three uploads, including the answer Flower gives when you forget the password:

**output**

```text
$ curl -u admin:change-me "localhost:5555/api/workers?refresh=1"   (summarised)
celery@vm  concurrency=2  queues=['default', 'ingest']  tasks registered=5

$ curl -u admin:change-me "localhost:5555/api/tasks"               (summarised)
states: {'SUCCESS': 3}
  ingest_document  SUCCESS  retries=0  runtime=1.04s
  ingest_document  SUCCESS  retries=0  runtime=1.01s
  ingest_document  SUCCESS  retries=2  runtime=1.01s

$ curl -o /dev/null -w "%{http_code}" localhost:5555/api/workers
401        (no credentials)
$ curl -o /dev/null -w "%{http_code}" -u admin:change-me localhost:5555/
200        (the dashboard)
```

> **Never expose Flower to the internet**
>
> Flower can **terminate tasks and shut workers down**, and it displays the arguments of every task, which may contain ids, emails or tokens. It refuses unauthenticated API access by default (the `401` above says so). Keep it behind a VPN or a reverse proxy with a login (Chapter 44), use a strong password, and never publish port 5555.


### What to watch

- **Queue length.** Messages waiting in `ingest`. A number that keeps growing means workers are too few, too slow, or absent. You can read it without Flower: `redis-cli llen ingest`. (During this chapter’s first real run, the worker had crashed, and `llen ingest` returned `3`: three uploads waiting for nobody. That one command found the problem in seconds.)
- **Retries.** A few are healthy. A task retrying constantly means a dependency is unwell.
- **Runtime.** If ingestion normally takes 2 seconds and suddenly takes 40, something upstream changed.
- **Failures.** Anything in the `FAILURE` state, plus documents in `failed` status in the database.
- **Workers online.** Zero workers is an outage, even though the website still loads.
Flower shows what is happening now. For history and alerts ("page me when the queue exceeds 100 for five minutes") you will add Sentry and metrics in Chapter 47.


## Testing Tasks

Running a real worker inside a test suite would be slow and fragile. Celery therefore has an **eager mode**: when `task_always_eager` is on, `.delay()` runs the task immediately, in the same process, with no broker. Combined with Django’s `captureOnCommitCallbacks`, which lets a test decide when the `on_commit` hooks run, you can test the whole flow in milliseconds:

**python  chat/tests/test_tasks.py (setup)**

```python
FAST = {"FAKE_PROCESSING_SECONDS": 0,
        "PASSWORD_HASHERS": ["django.contrib.auth.hashers.MD5PasswordHasher"]}

class CeleryTestMixin:
    """Run tasks immediately, in-process: no Redis, no worker needed."""

    def setUp(self):
        super().setUp()
        celery_app.conf.task_always_eager = True
        self.addCleanup(setattr, celery_app.conf, "task_always_eager", False)
        logging.disable(logging.CRITICAL)          # expected failures are noisy
        self.addCleanup(logging.disable, logging.NOTSET)
        self.ada = User.objects.create_user("ada", "ada@example.com", "pw-ada-1")

    def make_doc(self, filename, status=Document.Status.PROCESSING):
        return Document.objects.create(user=self.ada, filename=filename,
                                       status=status)

@override_settings(**FAST)
```

Test the things that actually break:

| **What to test** | **How (all in the suite below)** |
|---|---|
| The logic of each task | Create the rows, call `.delay()`, assert the rows changed |
| Idempotency | Run the task twice; the second run must do nothing (`"skipped"`) |
| Retries | Use the `flaky` and `timeout` files; assert the final state, not the number of calls |
| Permanent failures | Assert one attempt only and a useful `error` message |
| `on_commit` behaviour | `captureOnCommitCallbacks(execute=False)`: assert the job is **not** queued until commit |
| Broker down | Patch `.delay` to raise `OperationalError`; assert a `202` and a `failed` document, never a `500` |
| The schedule | Assert every Beat entry names a task that exists, and that routes point at the right queue |

> **What eager mode cannot catch**
>
> Eager mode skips the broker and the JSON serializer. A task called with an argument that cannot be turned into JSON (a model instance, a `datetime`) passes every eager test and fails in production. One more quirk we hit while writing this chapter: with `task_eager_propagates = True`, a task that retries raises the internal `Retry` exception straight into your test. Leave that setting off when you test retries. And always finish with a **real run**, as in Chapter 15, to prove the pieces work together.
