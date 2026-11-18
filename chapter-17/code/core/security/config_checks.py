"""Project-specific configuration checks.

Django's own `check --deploy` covers DEBUG, SECRET_KEY strength, HSTS and secure
cookies. These cover what it does not.
"""
from urllib.parse import urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}


def find_config_problems(settings) -> list[str]:
    """Return human-readable problems. `settings` is django.conf.settings."""
    problems: list[str] = []
    hosts = settings.ALLOWED_HOSTS
    if "*" in hosts or any(host.startswith(".*") for host in hosts):
        problems.append("ALLOWED_HOSTS contains a wildcard. List your real domains.")
    if getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False):
        problems.append("CORS_ALLOW_ALL_ORIGINS is True. List exact origins instead.")
    for origin in getattr(settings, "CORS_ALLOWED_ORIGINS", []):
        parts = urlsplit(origin)
        if parts.scheme != "https" and parts.hostname not in LOCAL_HOSTS:
            problems.append(f"CORS origin {origin} is not https.")
    for origin in getattr(settings, "CSRF_TRUSTED_ORIGINS", []):
        if urlsplit(origin).scheme != "https":
            problems.append(f"CSRF trusted origin {origin} is not https.")
    if "debug_toolbar" in settings.INSTALLED_APPS:
        problems.append("debug_toolbar is installed in a production configuration.")
    return problems
