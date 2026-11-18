# Chapter 17 — Backend Security and Best Practices: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Access Control: Who May Do What (A01) › The two-user test

Add this to `chat/test_security.py`. It logs in as Bo and tries everything against Ada’s conversation:

**chat/test_security.py**

```
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from chat import services

User = get_user_model()
BASE = "/api/v1/conversations"  # adjust to the URL layout of your Chapter 12 router
PASSWORD = "a-long-test-password"

class CrossUserAccessTests(APITestCase):
    def setUp(self):
        self.ada = User.objects.create_user(email="ada@example.com", password=PASSWORD)
        self.bo = User.objects.create_user(email="bo@example.com", password=PASSWORD)
        self.conversation = services.create_conversation(user=self.ada, title="Plans")
        self.url = f"{BASE}/{self.conversation.public_id}/"

    def test_anonymous_requests_are_rejected(self):
        self.assertEqual(self.client.get(BASE).status_code, 401)

    def test_other_users_get_404_not_403_for_someone_elses_object(self):
        self.client.force_authenticate(self.bo)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)  # 403 would confirm it exists

    def test_lists_never_contain_other_users_objects(self):
        self.client.force_authenticate(self.bo)
        response = self.client.get(BASE)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Plans", response.content.decode())

    def test_other_users_cannot_modify_or_delete(self):
        self.client.force_authenticate(self.bo)
        patch = self.client.patch(self.url, {"title": "Hacked"}, format="json")
        self.assertEqual(patch.status_code, 404)
        self.assertEqual(self.client.delete(self.url).status_code, 404)
```

Change `BASE` to match the URL layout of your Chapter 12 router. If your first authentication class is `SessionAuthentication`, anonymous requests get 403 instead of 401; adjust that one assertion.


## Access Control: Who May Do What (A01) › Server-side request forgery (SSRF)

AI apps fetch URLs: a document ingestion feature (Chapter 31), a tool that reads a web page (Chapter 30), a webhook you send to a customer’s address. If the URL comes from a user, a document or a model, an attacker can aim your server at things only your server can reach: the database on the private network, an admin panel on localhost, or the cloud metadata service at `169.254.169.254` that hands out credentials. That is **SSRF**, and OWASP now files it under access control.

The defence is to resolve the host name yourself and refuse anything that is not a public internet address. The function takes the DNS resolver as a parameter, which also lets us test it without a network:

**core/security/outbound.py**

```
"""Guard for server-side requests to URLs a user, document or model supplied (SSRF)."""
import ipaddress
import socket
from urllib.parse import urlsplit

class UnsafeURL(ValueError):
    """The URL points somewhere our server must not connect to."""

def validate_outbound_url(
    url: str, *, allowed_schemes=("https",), resolver=socket.getaddrinfo
) -> str:
    """Return the URL if it is safe to fetch from our servers; else raise UnsafeURL.

    Resolves the host name and refuses anything that is not a public internet
    address: private networks (10.x, 192.168.x), loopback (127.x), link-local
    (169.254.x, the cloud metadata service) and so on.
    """
    parts = urlsplit(url)
    if parts.scheme not in allowed_schemes:
        raise UnsafeURL(f"Only {', '.join(allowed_schemes)} URLs are allowed.")
    if not parts.hostname:
        raise UnsafeURL("The URL has no host name.")
    if parts.username or parts.password:
        raise UnsafeURL("URLs with embedded credentials are not allowed.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = resolver(parts.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURL("The host name could not be resolved.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped  # ::ffff:127.0.0.1 is really 127.0.0.1
        if not address.is_global:
            raise UnsafeURL("The URL resolves to a non-public address.")
    return url
```

Real output when it checks four URLs (the resolver is replaced by a stand-in that returns the address shown):

**text verified output**

```text
OK      https://example.com/doc.pdf
BLOCKED https://metadata.example/latest - The URL resolves to a non-public address.
BLOCKED https://intranet.example/admin - The URL resolves to a non-public address.
BLOCKED http://example.com/ - Only https URLs are allowed.
```

> **Validation is not the whole defence**
>
> Three gaps remain. **Redirects:** a safe URL can redirect to `http://169.254.169.254/`, so fetch with redirects disabled, or validate every hop. **DNS rebinding:** a host can answer with a public address when you check and a private one when you connect, so for high-risk features connect to the address you validated, or send fetches through an egress proxy that blocks private ranges. **Allow-lists beat block-lists:** if you only ever fetch from a few known sites, list them and refuse the rest.

WebSocket consumers (Chapter 14) need the same discipline: check ownership when the socket connects and again on every message that names an object.


## Hardening the Configuration (A02) › A deployment check of our own

`python manage.py check --deploy` is Django’s built-in audit. It already flags a weak `SECRET_KEY`, `DEBUG` on, a missing `ALLOWED_HOSTS`, no HSTS, no SSL redirect and insecure cookies. It does **not** know about our CORS rules, so we add checks for what it misses. The logic is a plain function (easy to test), and a three-line wrapper registers it with Django:

**core/security/config_checks.py**

```
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
```

**core/checks.py**

```
"""Registers our configuration checks, so `manage.py check --deploy` runs them."""
from django.conf import settings
from django.core.checks import Error, Tags, register

from .security.config_checks import find_config_problems

@register(Tags.security, deploy=True)
def project_security_checks(app_configs, **kwargs):
    problems = find_config_problems(settings)
    return [Error(problem, id="core.E001") for problem in problems]
```

Load the checks when Django starts by importing the module in `core/apps.py`:

**python core/apps.py**

```python
from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from . import checks  # noqa: F401  (importing registers the checks)
```

Because the check uses `Error`, a bad production configuration fails `check --deploy` with a non-zero exit code. Run it in CI (Chapter 42) and the pipeline stops before a risky configuration ships.


## Dependencies and the Supply Chain (A03) › Habits that remove most of the risk

1. **Pin and lock.** Chapter 11’s `requirements.txt` keeps Django on `>=6.1,<6.2`, so you receive security patches in 6.1.x without a surprise jump. The lock file records the exact versions that passed your tests. For stronger guarantees, tools such as `pip-tools` can add hashes and `pip install --require-hashes` refuses anything that does not match.
2. **Audit regularly.**  `pip-audit` checks your installed or locked packages against databases of known vulnerabilities. Run it before every release and in CI.
3. **Update on a schedule.** GitHub’s Dependabot opens pull requests for new versions and security advisories. Small, frequent updates are far easier than one giant upgrade after two years.
4. **Stay on a supported Django.** Django publishes security fixes as patch releases and announces them on the `django-announce` mailing list. Subscribe, and apply patch releases promptly. Check the supported-versions table on djangoproject.com as you did in Chapter 11.
5. **Vet every new dependency.** Before `pip install something`, ask: does it exist under exactly that name, is it actively maintained, who publishes it, and do I really need it? Prefer the standard library or a package you already trust.
6. **Protect the pipeline.** Give CI the minimum permissions, pin third-party GitHub Actions to a commit, and require reviews on the main branch (Chapter 42).
**bash terminal**

```bash
pip install pip-audit
pip-audit -r requirements.lock.txt      # known vulnerabilities in what you deploy
pip list --outdated                     # what has newer versions
```

**yaml .github/dependabot.yml**

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/backend"
    schedule:
      interval: "weekly"
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

When Chapter 18 adds the Next.js app, add an `npm` entry for the frontend folder in the same way, and a `docker` entry once you have Dockerfiles (Chapter 51).


## Passwords, Encryption and Tokens (A04, A07) › Encrypting what you must store

Some secrets have to be stored in a form you can read back, for example a customer’s own model-provider API key if your product lets users bring their own. Hashing will not work, because you need the original. Use **authenticated encryption**: Fernet, from the `cryptography` library, combines AES encryption with an integrity check, so tampering is detected instead of silently producing garbage. The keys live in the environment, never in the database that holds the encrypted values.

**core/security/crypto.py**

```
"""Encryption, token and signature helpers. Well-tested libraries only."""
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

class DecryptionError(Exception):
    """The data could not be decrypted: wrong key, or the stored value was changed."""

class SecretBox:
    """Encrypts short strings (such as a user's own provider API key) before storage.

    Fernet is authenticated encryption (AES plus an HMAC), so tampering is detected.
    The FIRST key encrypts; ALL keys can decrypt. That makes key rotation possible:
    put the new key first, re-encrypt with rotate(), then retire the old key.
    """

    def __init__(self, keys: list[str]):
        if not keys:
            raise ValueError("At least one encryption key is required.")
        self._fernet = MultiFernet([Fernet(key) for key in keys])

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise DecryptionError("Could not decrypt: wrong key or bad data.") from exc

    def rotate(self, token: str) -> str:
        """Re-encrypt a stored value with the newest key."""
        try:
            return self._fernet.rotate(token.encode()).decode()
        except InvalidToken as exc:
            raise DecryptionError("Could not rotate: wrong key or bad data.") from exc

def new_api_token(prefix: str = "aca") -> tuple[str, str]:
    """Create an API token. Returns (token_to_show_once, sha256_to_store).

    The token is long and random, so a fast hash is enough (unlike passwords, which
    need slow hashes). Store only the hash: a database leak then reveals no usable
    tokens.
    """
    token = f"{prefix}_{secrets.token_urlsafe(32)}"
    return token, hash_api_token(token)

def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def verify_hmac(
    secret: bytes, body: bytes, signature: str, *, algorithm: str = "sha256"
) -> bool:
    """Check a webhook signature: HMAC of the RAW body, compared in constant time."""
    expected = hmac.new(secret, body, getattr(hashlib, algorithm)).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())
```

A few points about this module:

- `SecretBox` takes a list of keys. The first key encrypts, and every key can decrypt. To rotate a key, put the new one first, run `rotate()` over the stored values, then retire the old key. Section 17.9 describes the rotation steps.
- `new_api_token` is for tokens you issue to your own users. The token is long and random, shown to the user once, and **only its SHA-256 hash is stored**. If the database leaks, the attacker gets hashes that cannot be turned back into usable tokens. A fast hash is fine here because the token has plenty of randomness; passwords need slow hashes because humans choose them.
- `verify_hmac` checks a webhook-style signature with `hmac.compare_digest`, which takes the same time whether the first byte or the last byte differs. Comparing with `==` can leak, through timing, how much of a guess was right. Section 17.10 uses it.
Create the key once and store it like any other secret:

**bash terminal**

```bash
python -c "from cryptography.fernet import Fernet as F; print(F.generate_key().decode())"
```

Then one tiny helper builds the box from settings, so the rest of the code never touches raw keys:

**python core/security/secretbox.py**

```python
from functools import lru_cache

from django.conf import settings

from .crypto import SecretBox

@lru_cache
def get_secret_box() -> SecretBox:
    return SecretBox(settings.FIELD_ENCRYPTION_KEYS)
```

A model that stores an encrypted value would keep the ciphertext in a text column, keep the last four characters separately for display, and never return the value from the API (write-only). Add `cryptography` to `requirements.txt` now.

> **Encryption does not replace access control**
>
> Encrypting a field protects you from someone who steals a database backup. It does **not** protect you from a bug that lets user A read user B’s row through your own application, because the application decrypts the value for whoever it believes is asking. Access control (17.3) and encryption solve different problems; you need both.


## Injection and Input Sanitization (A05) › SQL injection

Django’s ORM sends every value separately from the SQL text, so ordinary queries cannot be injected. The danger is the escape hatches: `.raw()`, `.extra()`, `RawSQL` and `cursor.execute()` with a string you built yourself.

**python raw SQL: the wrong way and the right way**

```python
# DANGEROUS: the title becomes part of the SQL text ("' OR '1'='1" returns every row)
Conversation.objects.raw(f"SELECT * FROM chat_conversation WHERE title = '{title}'")

# SAFE: the database driver sends the value separately from the SQL
Conversation.objects.raw("SELECT * FROM chat_conversation WHERE title = %s", [title])
```

Django itself has fixed SQL-injection bugs in rarely used corners, usually when attacker-controlled dictionary keys or column names reached methods like `annotate()` or `values()`. That is one more reason to apply patch releases (17.5) and never pass user input as keyword argument names.


## Injection and Input Sanitization (A05) › Cleaning text and file names

`clean_text` is for titles, names and other short fields: it removes control characters and the Unicode "bidi" tricks that can disguise a file name or title, normalizes accents, and **rejects** over-long input instead of silently cutting it. Do **not** use it to rewrite chat messages: the model needs exactly what the user typed, so store messages as they are and escape them when they are displayed.

`safe_filename` is for uploads (Chapter 16): it removes any directory part (so `../../etc/passwd` becomes `passwd`), replaces odd characters, and keeps a short extension. Even so, the safest design is to **store files under a random name** (a UUID) and keep the original name only as display text.

| **Upload risk** | **Defence (details in Chapter 16)** |
|---|---|
| A file name with `../` or odd characters | `safe_filename`, and storage under random names |
| A harmful file disguised as an image | Allow-list of types, check the content and not just the extension or `Content-Type` |
| Huge files | A size limit enforced in the view or serializer and at the proxy (Django has no maximum-file-size setting) |
| Files executed or shown as web pages | Private bucket, served with `Content-Disposition: attachment` from a different domain |


## Rate Limiting and Abuse Prevention (A06) › What to limit, and where to start

These are starting points to tune with real traffic, not magic numbers. Be stricter where a mistake costs more:

| **Action** | **Suggested starting limit** | **Key to count by** |
|---|---|---|
| Login attempts | 5 per 15 minutes | email (hashed) **and** IP address |
| Sign-up | 5 per hour | IP address |
| Password reset, verification emails | 3 per hour per email, 10 per hour per IP | email (hashed) and IP address |
| Chat messages | 10 per minute | user |
| AI tokens | A daily budget per user or plan | user |
| Unauthenticated API use | 60 per minute | IP address |

Emails deserve special care: every email you send costs money and can be used to harass a stranger, so limit the endpoints that trigger them. Two details for the login limit. First, **count by both the account and the address**, so that one address cannot try many accounts and many addresses cannot hammer one account. Second, **do not lock an account hard**: an attacker could then lock out real users on purpose. Slow them down instead. Hash the email before using it in a key, which keeps personal data out of Redis:

**python login throttling (the pattern; Chapter 13 owns the view)**

```python
import hashlib

email_key = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]
limiter = get_limiter()
by_account = limiter.hit("login_account", f"{email_key}:{ip}", limit=5, window=900)
by_address = limiter.hit("login_ip", ip, limit=30, window=900)
if not (by_account.allowed and by_address.allowed):
    raise Throttled(wait=max(by_account.retry_after, by_address.retry_after))
```


## Secrets Management › Take inventory

| **Secret** | **Where it lives** | **Notes** |
|---|---|---|
| `DJANGO_SECRET_KEY` | Environment of the running app | Signs sessions and reset links; different in every environment |
| Database and Redis passwords | `DATABASE_URL`, `REDIS_URL` | Each environment has its own user and password |
| Model-provider API key | Environment, backend only | Create a restricted key per environment and set a spending limit |
| Stripe and Paystack secret keys, webhook secrets | Environment, backend only | Use **test** keys everywhere except production; restricted keys where offered |
| Object storage and email keys | Environment | Scope to one bucket or one sending domain |
| `FIELD_ENCRYPTION_KEYS` | Environment | Losing it means losing the encrypted data: back it up in your password manager |
| GitHub, Docker and server credentials | A password manager, CI secret store | Never in the repository |


## Logging and Audit Trails (A09) › Redaction and structured logs

Chapter 11 gave every log line a request id. Two additions make logs safe and searchable. A **redaction filter** masks things that look like secrets (JWTs, bearer tokens, provider keys, `password=...` pairs) and escapes line breaks so a user cannot forge extra log lines. A **JSON formatter** writes one JSON object per line, which log tools can filter by field. It redacts the **data** before turning it into text, so the output is always valid JSON, and it masks fields by name (`api_key`, `access_token`) while leaving counters like `input_tokens` alone.

**core/security/redaction.py**

```
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
```

Real output from the filter and the formatter. Notice the forged log line is neutralized, the key is masked, and the token counter survives. (The last entry is a single line in real logs; it is wrapped here to fit the page.)

**text verified output**

```text
INFO provider call failed, key=[KEY REDACTED]
INFO login failed for evil@example.com\nINFO forged: admin logged in
INFO retry with password=[REDACTED] and Authorization: [REDACTED]
{"time": "2026-11-03T01:15:05.086+00:00", "level": "INFO", "logger": "demo2",
 "request_id": "req_0b78754d712b", "message": "message saved",
 "event": "chat.message_saved",
 "fields": {"input_tokens": 120, "api_key": "[REDACTED]"}}
```

Update the `LOGGING` setting from Chapter 11 to use both. JSON is the default outside development, because that is what Docker and Dokploy collect:

**python config/settings.py (replace LOGGING)**

```python
LOG_JSON = env.bool("DJANGO_LOG_JSON", default=not DEBUG)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "core.log_filters.RequestIDFilter"},
        "redact": {"()": "core.security.redaction.RedactionFilter"},
    },
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"
        },
        "json": {"()": "core.security.redaction.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if LOG_JSON else "standard",
            "filters": ["request_id", "redact"],
        },
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
    "loggers": {
        # DisallowedHost, suspicious requests, CSRF failures
        "django.security": {"level": "INFO"},
    },
}
```

Redaction is a safety net with limits: it recognises common shapes, not every secret. The real defence is the table above: do not log secrets in the first place.


## Logging and Audit Trails (A09) › What to audit, and what not to

| **Audit this** | **Do not write to the audit table** |
|---|---|
| Logins (success and failure), password changes, new API tokens | Every rate-limited request: it belongs in the logs and metrics |
| Role and permission changes, staff actions | Every successful read of ordinary data |
| Deleting or exporting user data, account deletion | Message text, prompts or model output |
| Refunds, plan changes, billing events | Anything an attacker can trigger thousands of times a minute |

The last row is a real design point. If an attacker can make your application write a database row per request, the audit table becomes a way to fill your disk. Count and alert on high-volume events (below); audit the **rare, important** ones.


## Logging and Audit Trails (A09) › Alerts: a log nobody reads is not a control

Chapter 55 sets up Sentry and uptime monitoring. These are the signals worth an alert, in rough order of value:

| **Signal** | **What it may mean** |
|---|---|
| Sudden rise in 401 or failed-login events | Credential stuffing or a password-guessing attack |
| Many 403 or 404 responses from one user or address | Someone probing for other users’ objects (IDOR) |
| Rising 429 responses | A script hitting your limits, or limits set too tight for real users |
| 5xx rate above normal | A bug, an outage, or an input that breaks your code |
| New staff login from an unfamiliar address, or any `access.role_changed` event | Account takeover or privilege escalation |
| Failed webhook signatures | Someone forging provider events |


## Logging and Audit Trails (A09) › Privacy and retention

Logs and audit rows contain personal data: IP addresses count as personal data under laws such as the GDPR and Nigeria’s Data Protection Act. Keep only what you need, for as long as you need it, and write the period down (Chapter 34). A common pattern is short retention for application logs, a longer one for the audit trail, and deletion by a scheduled job (Chapter 15) that removes rows older than the policy allows.

> **"Append-only" in Python is a seat belt, not a vault**
>
> Overriding `save()` and `delete()` stops honest mistakes, but `AuditEvent.objects.filter(...).delete()` and `.update()` bypass those methods, and anyone with database access can change rows. The admin above refuses changes, but for a stronger guarantee enforce it in the database: give the application’s database user only `INSERT` and `SELECT` on the audit table, or add a PostgreSQL trigger that rejects `UPDATE` and `DELETE`. Then run retention cleanup with a separate, privileged maintenance role.
