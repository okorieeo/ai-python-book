import os
 
from core.observability.sentry_scrub import init_sentry
 
init_sentry(
    os.environ.get("SENTRY_DSN"),             # empty in development: Sentry stays off
    environment=os.environ.get("APP_ENV", "production"),
    release=os.environ.get("APP_VERSION", "dev"),
    traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
)
