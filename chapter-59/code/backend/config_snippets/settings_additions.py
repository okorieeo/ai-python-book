# config/settings.py (additions for Chapter 59)
INSTALLED_APPS += ["tasks", "schedule", "assistant"]   # NOT "calendar": that name shadows Python's own module

ASSISTANT_MODEL = env("ASSISTANT_MODEL", default="claude-sonnet-5-5")  # check Anthropic's docs for current names

CELERY_BEAT_SCHEDULE = {
    "event-and-task-reminders": {"task": "assistant.tasks.send_due_reminders", "schedule": 60.0},
    "daily-briefings": {"task": "assistant.tasks.send_daily_briefings", "schedule": 300.0},
}
