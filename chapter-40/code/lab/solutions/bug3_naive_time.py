from datetime import datetime, timedelta, timezone

TRIAL = timedelta(days=14)


def is_trial_active(started_at: datetime, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)      # store and compare time-zone aware UTC values
    return now - started_at < TRIAL
