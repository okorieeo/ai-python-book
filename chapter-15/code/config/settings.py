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
# ----- next listing from the chapter -----
CELERY_BEAT_SCHEDULE = {
    "purge-idempotency-keys": {
        "task": "chat.tasks.purge_idempotency_keys",
        "schedule": crontab(minute=0),                        # every hour
    },
    "fail-stuck-documents": {
        "task": "chat.tasks.fail_stuck_documents",
        "schedule": crontab(minute="*/10"),                   # every 10 minutes
    },
    "purge-deleted-conversations": {
        "task": "chat.tasks.purge_deleted_conversations",
        "schedule": crontab(hour=3, minute=30),               # 03:30 UTC daily
    },
    "daily-usage-report": {
        "task": "chat.tasks.daily_usage_report",
        "schedule": crontab(hour=6, minute=0),                # 06:00 UTC daily
    },
}
