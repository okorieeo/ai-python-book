"""Keep chat content, credentials and personal data out of error reports.

Sentry's defaults are sensible, but an AI chat app handles unusually sensitive text.
`before_send` is the last chance to remove it. Standard library only; sentry_sdk is imported
only inside init_sentry, so these functions are testable without it.
"""
from __future__ import annotations

import re
from typing import Any, Callable

SENSITIVE_KEY = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|cookie|session"
    r"|csrf|credential|private[_-]?key)",
    re.IGNORECASE,
)
CONTENT_KEYS = {
    "prompt", "prompts", "messages", "message_text", "content", "completion", "completions",
    "system_prompt", "user_message", "assistant_message", "response_text",
}
# Counters such as input_tokens contain the word "token" but are not secrets (Chapter 17).
COUNTER_KEY = re.compile(
    r"^((input|output|total|prompt|completion|max|cache_\w+)_?tokens(_\w+)?"
    r"|tokens_(used|count|in|out))$",
    re.IGNORECASE,
)
REDACTED = "[REDACTED]"
CONTENT_REMOVED = "[CONTENT REMOVED]"


def _default_redact_text(text: str) -> str:
    try:  # Chapter 17's redaction, when available
        from core.security.redaction import redact
        return redact(text)
    except Exception:  # noqa: BLE001
        pattern = r"(?i)(bearer\s+|password=|token=|api[_-]?key=)\S+"
        return re.sub(pattern, r"\1" + REDACTED, text)


def _values(section) -> list:
    """The `values` list of a breadcrumbs or exception section ([] if missing or odd)."""
    return section.get("values", []) if isinstance(section, dict) else []


def _masked_header(name: str) -> bool:
    return bool(SENSITIVE_KEY.search(name)) or name.lower() == "x-forwarded-for"


def scrub_value(value: Any, key: str = "") -> Any:
    """Mask by key name: credentials -> [REDACTED], chat content -> [CONTENT REMOVED]."""
    if key and COUNTER_KEY.match(key):
        return value
    if key and SENSITIVE_KEY.search(key):
        return REDACTED
    if key.lower() in CONTENT_KEYS:
        return CONTENT_REMOVED
    if isinstance(value, dict):
        return {k: scrub_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub_value(v, key) for v in value]
    return value


def scrub_event(event: dict, hint: dict | None = None,
                redact_text: Callable[[str], str] | None = None):
    """Use as before_send and before_send_transaction. Returns the cleaned event."""
    redact_text = redact_text or _default_redact_text
    request = event.get("request")
    if isinstance(request, dict):
        for field in ("data", "cookies", "query_string"):
            request.pop(field, None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                k: (REDACTED if _masked_header(k) else v) for k, v in headers.items()
            }
        env = request.get("env")
        if isinstance(env, dict):
            env.pop("REMOTE_ADDR", None)
    user = event.get("user")
    if isinstance(user, dict):
        event["user"] = {"id": user["id"]} if "id" in user else {}
    for section in ("extra", "contexts", "tags"):
        if isinstance(event.get(section), dict):
            event[section] = scrub_value(event[section])
    for crumb in _values(event.get("breadcrumbs")):
        if isinstance(crumb.get("data"), dict):
            crumb["data"] = scrub_value(crumb["data"])
        if isinstance(crumb.get("message"), str):
            crumb["message"] = redact_text(crumb["message"])
    for exc in _values(event.get("exception")):
        if isinstance(exc.get("value"), str):
            exc["value"] = redact_text(exc["value"])
        for frame in (exc.get("stacktrace") or {}).get("frames", []):
            frame.pop("vars", None)
    if isinstance(event.get("message"), str):
        event["message"] = redact_text(event["message"])
    return event


def init_sentry(dsn: str | None, *, environment: str, release: str,
                traces_sample_rate: float = 0.0, sdk=None) -> bool:
    """Start Sentry if a DSN is configured; return False and do nothing otherwise."""
    if not dsn:
        return False
    if sdk is None:
        import sentry_sdk as sdk  # type: ignore[no-redef]
    sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        traces_sample_rate=traces_sample_rate,
        before_send=scrub_event,
        before_send_transaction=scrub_event,
    )
    return True
