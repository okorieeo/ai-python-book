# Chapter 12 — Building REST APIs with Django REST Framework: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Project Setup › The REST_FRAMEWORK settings

Everything global about the API lives in one settings block. Read it slowly; each line is a decision from Chapter 8:

**python  config/settings.py (added at the end)**

```python
# ------------------------------------------------------------------ the API
AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "api.pagination.StandardCursorPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/min", "user": "300/min", "ai_chat": "20/min", "auth": "10/min",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "api.errors.api_exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",       # tests send JSON like real clients
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AI Chat API",
    "DESCRIPTION": "REST API for the AI Chat SaaS. Every path lives under /api/v1.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]

CHAT_DAILY_TOKEN_LIMIT = 50_000
CLIENT_CONFIG = {
    "min_supported_version": "1.0.0",
    "latest_version": "1.0.0",
    "maintenance_mode": False,
}
```

| **Setting** | **Decision it records** |
|---|---|
| `DEFAULT_AUTHENTICATION_CLASSES` | JWT bearer tokens only. The first class decides what an unauthenticated response looks like: with JWT, DRF answers `401` with a `WWW-Authenticate` header, while session authentication would answer `403` |
| `DEFAULT_PERMISSION_CLASSES` | `IsAuthenticated`: every view is **closed** unless it explicitly opts out |
| `DEFAULT_RENDERER_CLASSES` / `PARSER_CLASSES` | JSON in, JSON out. No browsable HTML API in production, and no form posts until uploads arrive in Chapter 16 |
| `DEFAULT_PAGINATION_CLASS` | Every list endpoint is paginated by default, so forgetting to configure one cannot produce an unbounded list |
| `DEFAULT_FILTER_BACKENDS` | Filtering, ordering and search are available, but each view must still whitelist its fields |
| `DEFAULT_THROTTLE_*` | Anonymous and per-user limits, plus named scopes for expensive endpoints |
| `EXCEPTION_HANDLER` | One function shapes every error (section 12.7) |
| `TEST_REQUEST_DEFAULT_FORMAT` | Tests send JSON, like real clients. Without it, DRF’s test client posts multipart forms and your JSON-only parser answers `415` |

Finally add the apps and the middleware to `INSTALLED_APPS` and `MIDDLEWARE` (the complete file is in the companion code), then create and apply the migrations:

**terminal**

```bash
python manage.py makemigrations accounts chat
python manage.py migrate
```


## Serializers › Reading the code

- `id = UUIDField(source="public_id")` renames a model field for the outside: clients see `id`, the database keeps both `id` and `public_id`.
- `fields` **is an explicit list.** Never `"__all__"`: a column added next month must not become public by accident.
- `read_only_fields` can be seen but not set. A client that sends `"message_count": 99` is silently ignored. That is the whole defence against mass assignment, and a test proves it.
- `validate_title` is a **field-level validator**: the method name `validate_<field>` is the convention. It trims whitespace and rejects an empty result. It runs after the built-in checks (`max_length`, `required`).
- **Two serializers for messages.**  `MessageSerializer` is what the client reads (role, token counts, timestamps). `MessageCreateSerializer` is what the client sends: the text and nothing else. The server alone decides the role and the token counts.
- `DocumentSerializer.validate_filename` returns a clear message listing the allowed extensions, which the web or mobile form can show beside the input.
- `ErrorSerializer` is never used to parse anything. It exists so the documentation shows the error shape of Chapter 8 on every endpoint.

## Idempotency and Long-Running Work › The idempotency decorator

Section 8.4 explained why a retried `POST` must not run twice. Here is the implementation, a decorator you can put on any view method:

**python  api/idempotency.py**

```python
import hashlib
import json
from functools import wraps

from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from chat.models import IdempotencyKey

class Conflict(APIException):
    status_code = 409
    default_code = "conflict"

def idempotent(view_method):
    """Replay the saved answer when a client retries with the same key."""

    @wraps(view_method)
    def wrapper(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key:
            return view_method(self, request, *args, **kwargs)
        if len(key) > 200:
            raise ValidationError({"Idempotency-Key": ["Too long."]})
        payload = json.dumps(request.data, sort_keys=True, default=str)
        digest = hashlib.sha256(f"{request.path}{payload}".encode()).hexdigest()

        record, created = IdempotencyKey.objects.get_or_create(
            user=request.user, key=key, defaults={"request_hash": digest}
        )
        if not created:                               # a retry
            if record.request_hash != digest:
                raise Conflict("This key was used for a different request.")
            if record.response_status is None:
                raise Conflict("The first request is still running.")
            return Response(record.response_body, status=record.response_status,
                            headers={"Idempotent-Replay": "true"})

        try:
            response = view_method(self, request, *args, **kwargs)
        except Exception:
            record.delete()                           # failed: allow a clean retry
            raise
        record.response_status = response.status_code
        record.response_body = response.data
        record.save(update_fields=["response_status", "response_body"])
        return response

    return wrapper
```

Read it in four steps:

1. **No header, no change.** Without an `Idempotency-Key`, the decorator does nothing and the view runs normally.
2. **Fingerprint the request.** The digest covers the URL path and the canonical JSON body. The same key with a different body is a client bug.
3. **Claim the key atomically.**  `get_or_create` relies on the database’s unique constraint `(user, key)`. If two retries arrive at the same instant, only one `created=True` result exists. The other sees an existing row.
4. **Replay or run.** A finished key returns the saved status and body with `Idempotent-Replay: true`. A different body returns `409`. A key whose first request is still running also returns `409`. Otherwise the view runs, and its response is saved.
| **Situation** | **Result** |
|---|---|
| First request with a new key | Runs normally; the response is stored under the key |
| Retry with the same key and body | The stored response, `Idempotent-Replay: true`, no second row |
| Same key, different body | `409 conflict`: the client reused a key by mistake |
| Same key while the first is running | `409 conflict`: try again shortly |
| First request failed with an exception | The key is deleted so a clean retry can succeed |

Keys are scoped to the user, so two people can use the same value without clashing, and a scheduled Celery job (Chapter 15) deletes keys older than 24 hours. Add `@idempotent` to any other costly `POST` the same way (checkout in Chapters 35 to 38 is the next candidate).


## Documenting with drf-spectacular

Section 8.10 introduced OpenAPI. With `drf-spectacular` most of the file writes itself: it reads your serializers, viewsets and filters and produces the description. The wiring is the `DEFAULT_SCHEMA_CLASS` setting, the `SPECTACULAR_SETTINGS` block and three URLs, all already in the files above. You add `@extend_schema` and `@extend_schema_view` only where the tool cannot guess: summaries, the shared error responses, request bodies that differ from the response, and actions without a serializer.

- `COMPONENT_SPLIT_REQUEST` produces separate `...Request` and response schemas, so read-only fields such as `id` and `created_at` are not shown as things the client can send.
- `ErrorSerializer` attached to the `400`, `401`, `404` and `429` responses documents the error shape on every endpoint.
- `queryset = Model.objects.none()` on viewsets that override `get_queryset()` silences the warning "Failed to obtain model through view’s queryset". Without it the generator calls your method with an anonymous user.
**terminal**

```bash
python manage.py spectacular --file docs/openapi.generated.yaml \
  --validate --fail-on-warn
```

`--validate` checks the output against the OpenAPI specification and `--fail-on-warn` turns the tool’s warnings into errors. One of the tests in Chapter 12 runs exactly this, so a view that breaks the documentation breaks the build. The generated file is about 1,100 lines, produced from a few hundred lines of code. Open `http://localhost:8000/api/docs/` for Swagger UI or `/api/redoc/` for ReDoc, and generate TypeScript types for the Next.js and React Native apps from `/api/schema/` as shown in section 8.10.

> **Compare the contract with reality**
>
> Open Chapter 8’s hand-written `openapi.yaml` next to the generated file. The differences are your review checklist: a path missing from the generated file is something you designed but have not built, and a path missing from the hand-written one is something you built without designing. In Chapter 42 a CI job runs this comparison for you.

> **Protect the docs in production**
>
> Swagger UI is a map of your whole API. Public APIs often publish it on purpose. A private API should serve it only to staff, or only in staging, by giving the three documentation views `permission_classes` of your choosing (`SpectacularAPIView.as_view(permission_classes=[IsAdminUser])`).
