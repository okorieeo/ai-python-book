# Add to config/settings.py
from obs.logpolicy import ContentLogPolicy

# Conversation CONTENT in logs. "off" is the default; "all" raises an error in production.
AI_CONTENT_LOG = ContentLogPolicy(mode="off", environment="production")     # try mode="errors" while debugging

AI_HOURLY_BUDGET_MICRO_USD = 5_000_000          # $5 an hour: set to a few times your normal busy hour

# Celery Beat (Chapter 15)
CELERY_BEAT_SCHEDULE = {
    "ai-health": {"task": "obs.jobs.check_ai_health", "schedule": 300.0},    # every 5 minutes
}
