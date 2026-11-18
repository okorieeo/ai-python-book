"""Symptom: works on the developer's laptop, raises TypeError in production (and is wrong in some time zones)."""
from datetime import datetime, timedelta

TRIAL = timedelta(days=14)


def is_trial_active(started_at: datetime, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    return now - started_at < TRIAL
