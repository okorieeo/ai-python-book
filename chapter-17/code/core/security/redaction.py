"""Keep secrets and forged lines out of the logs."""
import json
import logging
import re
from datetime import datetime, timezone

# Order matters: the most specific patterns first.
_PATTERNS = [
    # a whole Authorization header value, whatever the scheme (Bearer, Basic, Token...)
    (
        re.compile(r"""(?i)\b(authorization)\b(["']?\s*[:=]\s*["']?)[^\r\n"',}\\]+"""),
        r"\1\2[REDACTED]",
    ),
    (re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+"), "[JWT REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{8,}"), "[KEY REDACTED]"),
    (re.compile(r"\bwhsec_[A-Za-z0-9]{8,}"), "[KEY REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "[KEY REDACTED]"),
]
# key=value or "key": "value" pairs whose key name suggests a secret
_KEY_VALUE = re.compile(
    r"""(?ix)\b(password|passwd|secret|token|api[_-]?key)\b
        (["']?\s*[:=]\s*["']?)([^\s"',;&}\\]+)"""
)
# Field NAMES that always hold secrets. input_tokens or tokens_used do not match:
# they are counters, not secrets.
_SENSITIVE_KEY = re.compile(
    r"(?i)^(.*[_-])?(password|passwd|secret|secret[_-]?key|token|api[_-]?key"
    r"|authorization)$"
)


def redact(text: str) -> str:
    """Mask secret-looking text: JWTs, bearer tokens, keys, password=... pairs."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)


def redact_data(value, key: str = ""):
    """Redact dicts, lists and strings: by field name first, then by string shape."""
    if _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_data(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_data(v, key) for v in value]
    return value


def neutralize_newlines(text: str) -> str:
    """Stop a user forging extra log lines by putting line breaks in their input."""
    return text.replace("\r", "\\r").replace("\n", "\\n")


class RedactionFilter(logging.Filter):
    """Redacts secrets and escapes line breaks in every message (not in tracebacks)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # a bad format string must never break logging
            message = str(record.msg)
        record.msg = neutralize_newlines(redact(message))
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line: easy for Docker, Dokploy and log tools to search."""

    def format(self, record: logging.LogRecord) -> str:
        created = datetime.fromtimestamp(record.created, timezone.utc)
        payload = {
            "time": created.isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        # optional: logger.info("...", extra={"event": "login_failed", "fields": {...}})
        for extra in ("event", "fields"):
            if hasattr(record, extra):
                payload[extra] = getattr(record, extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # redact the data first, then serialize: the output is always valid JSON
        return json.dumps(redact_data(payload), default=str)
