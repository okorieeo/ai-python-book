# Chapter 11 — Django Fundamentals: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## What Is Django, and Why Use It? › Alternatives, briefly

| **Framework** | **Strengths** | **Trade-off** |
|---|---|---|
| **FastAPI** | Modern, async-first, automatic OpenAPI, great for small API services and ML model serving | You assemble auth, admin, ORM and migrations yourself |
| **Flask** | Minimal and flexible | Same: you choose and integrate every part |
| **Node (NestJS, Express)** | One language across frontend and backend | Weaker fit for AI/data libraries; less built in |

None of these is wrong. For a product with users, billing, an admin, background jobs and AI, Django’s completeness wins. (Nothing stops you from adding a FastAPI microservice later for something specialized; Chapter 6’s modular design leaves room.)


## Views, URLs and Templates › Function-based vs. class-based views

**python**

```python
# function-based: simplest, explicit
def ping(request):
    return JsonResponse({"ping": "pong"})

# class-based: one method per HTTP verb, reusable through inheritance
from django.views import View

class Ping(View):
    def get(self, request):
        return JsonResponse({"ping": "pong"})
```

In Chapter 12 we move to **Django REST Framework**, whose class-based `APIView` and `ViewSet` build on these ideas and add serializers, authentication, permissions, pagination and throttling. Learning plain Django views first means you know what DRF is doing for you.


## The Service Layer › Reading the design

- **Keyword-only arguments** (`*,`) make calls self-documenting and prevent argument-order mistakes: `create_conversation(user=ada, title="Trip")`.
- **Services raise plain Python exceptions** (`ValueError`, `DoesNotExist`). They know nothing about HTTP. The view (or consumer) translates them into `400` or `404`. That keeps services reusable from REST views, WebSocket consumers and Celery tasks.
- `get_conversation_for_user` implements the IDOR defence from Chapter 8: it cannot return someone else’s data, because the owner is part of the query.
- `transaction.atomic()` ensures the message and the usage record are created together or not at all.
- `tokens_used_this_month` reads the **ledger** (`UsageRecord`) with one aggregate query. In Chapter 35 this is what enforces plan limits.
Notice what is missing: no `request`, no `JsonResponse`, no serializers. That is deliberate.


## Testing Django Code › Testing the model manager

**accounts/tests.py**

```
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

User = get_user_model()

class UserManagerTests(TestCase):
    def test_create_user_normalizes_email_and_hashes_password(self):
        user = User.objects.create_user(email="Ada@Example.COM", password="a-long-test-password")
        self.assertEqual(user.email, "ada@example.com")
        self.assertNotEqual(user.password, "a-long-test-password")      # stored as a hash
        self.assertTrue(user.check_password("a-long-test-password"))
        self.assertFalse(user.is_staff)

    def test_email_must_be_unique_ignoring_case(self):
        User.objects.create_user(email="ada@example.com", password="a-long-test-password")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(email="ADA@example.com", password="another-long-password")

    def test_email_is_required(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="a-long-test-password")

    def test_create_superuser_sets_flags(self):
        admin_user = User.objects.create_superuser(email="root@example.com", password="a-long-test-password")
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
```


## Testing Django Code › Testing the health view and middleware

**core/tests.py**

```
from django.test import TestCase

class HealthTests(TestCase):
    def test_health_returns_ok_and_request_id(self):
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})
        self.assertTrue(response["X-Request-ID"].startswith("req_"))

    def test_valid_incoming_request_id_is_kept(self):
        response = self.client.get("/api/v1/health", headers={"X-Request-ID": "abc-12345678"})
        self.assertEqual(response["X-Request-ID"], "abc-12345678")

    def test_invalid_incoming_request_id_is_replaced(self):
        response = self.client.get("/api/v1/health", headers={"X-Request-ID": "bad id with spaces!"})
        self.assertTrue(response["X-Request-ID"].startswith("req_"))

    def test_health_only_allows_get(self):
        response = self.client.post("/api/v1/health")
        self.assertEqual(response.status_code, 405)
```


## Testing Django Code › What these tests demonstrate

| **Test** | **Rule it protects** |
|---|---|
| `test_user_cannot_read_someone_elses_conversation` | Ownership scoping (no IDOR) |
| `test_assistant_reply_creates_message_and_usage_together` | Billing consistency |
| `test_usage_ignores_previous_months_and_other_users` | Correct monthly window and per-user totals |
| `test_usage_is_a_single_query` | Performance guard (`assertNumQueries`) |
| `test_email_must_be_unique_ignoring_case` | Database constraint, not only application code |
| `test_invalid_incoming_request_id_is_replaced` | Untrusted input (headers) is validated |

> **pytest is a fine alternative**
>
> Many teams prefer **pytest** with the `pytest-django` plugin for shorter tests, fixtures and parametrization. Django’s built-in runner keeps this chapter dependency-free; Chapter 39 introduces pytest, factories and coverage. The test bodies you write today translate easily.

> **Tests in CI**
>
> Continuous integration needs the same environment variables (`DJANGO_SECRET_KEY`, `DATABASE_URL` and so on) and a PostgreSQL service. If you set `DJANGO_DEBUG=false` in CI, also set `DJANGO_SECURE_SSL_REDIRECT=false`, or the test client’s plain HTTP requests may be redirected. Chapter 42 builds the GitHub Actions pipeline.


## Developer Tooling › Pre-commit hooks (optional but recommended)

A `pre-commit` configuration can run `ruff` and the tests’ fast checks before each commit, so broken code never reaches the repository. We set this up with CI in Chapter 42.
