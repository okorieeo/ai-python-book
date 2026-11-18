INSTALLED_APPS += ["privacy"]

# ---------------------------------------------------------------- responsible AI (Chapter 34)
# The reviewed text shown to someone in crisis. Write it with care; put verified local resources in it.
SAFETY_SUPPORT_MESSAGE = env("SAFETY_SUPPORT_MESSAGE")
# A random string placed in the system prompt; if it ever appears in output, the prompt leaked.
PROMPT_CANARY = env("PROMPT_CANARY")          # e.g. REF- plus 16 hex characters (chat.ai_pipeline.new_canary)

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update({"privacy_export": "3/hour", "privacy_delete": "3/day"})

CELERY_BEAT_SCHEDULE.update({
    "run-due-deletions": {"task": "privacy.tasks.run_due_deletions", "schedule": 3600},
    "purge-ai-logs": {"task": "privacy.tasks.purge_expired", "schedule": 86400,
                      "args": ("chat.AIRequestLog", "ai_request_logs")},
    "purge-flagged": {"task": "privacy.tasks.purge_expired", "schedule": 86400,
                      "args": ("chat.FlaggedMessage", "flagged_for_review")},
})
