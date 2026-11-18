"""Add these to your Django settings (Chapter 51 layout). Values come from environment variables (Chapter 54)."""
import os

INSTALLED_APPS_EXTRA = ["django.contrib.postgres", "docuask"]       # 'django.contrib.postgres' is needed for GIN and full-text search

ANSWER_MODEL = os.environ.get("ANSWER_MODEL", "claude-sonnet-5-5")
FAST_MODEL = os.environ.get("FAST_MODEL", "claude-haiku-5-5")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "voyage-4")
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))   # changing this means re-embedding every chunk

# ANTHROPIC_API_KEY and VOYAGE_API_KEY are read from the environment by their SDKs. Never put them in code.

REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {"ask": "20/min"},                  # a second brake on top of the monthly plan quota
}

DATA_UPLOAD_MAX_MEMORY_SIZE = 110 * 1024 * 1024                   # at least the largest plan's file size, and no more than your proxy allows
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024                     # bigger files are streamed to disk instead of held in memory

CELERY_TASK_ROUTES = {"docuask.tasks.ingest_document": {"queue": "ingest"}}   # its own queue: a big upload must not delay chat tasks
CELERY_WORKER_PREFETCH_MULTIPLIER = 1                             # long tasks: take one at a time
