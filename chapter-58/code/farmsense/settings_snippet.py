"""Add to your Django settings (Chapter 51 layout)."""
from celery.schedules import crontab

INSIGHT_MODEL = "claude-sonnet-5-5"          # check Anthropic's current model list before deploying

CELERY_BEAT_SCHEDULE = {
    "evaluate-alert-rules": {"task": "farmsense.tasks.evaluate_rules", "schedule": 60.0},
    "ensure-partitions": {"task": "farmsense.tasks.ensure_partitions", "schedule": crontab(hour=1, minute=10)},
    "drop-old-partitions": {"task": "farmsense.tasks.drop_old_partitions", "schedule": crontab(day_of_week=0, hour=2, minute=30)},
    "daily-reports": {"task": "farmsense.tasks.daily_reports", "schedule": crontab(minute=5)},   # hourly; each farm is handled after ITS midnight
}
CELERY_TASK_ROUTES = {"farmsense.tasks.evaluate_rules": {"queue": "alerts"}, "farmsense.tasks.notify": {"queue": "alerts"}}
# Alerts get their own queue and worker: a slow report must never delay a fire alarm.
#   celery -A config worker -Q alerts -c 2        celery -A config worker -Q celery -c 2        celery -A config beat

REST_FRAMEWORK = {"DEFAULT_THROTTLE_RATES": {"device": "120/min", "user": "300/min"}}
