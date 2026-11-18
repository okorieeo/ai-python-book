CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {"chat.tasks.ingest_document": {"queue": "ingest"}}
