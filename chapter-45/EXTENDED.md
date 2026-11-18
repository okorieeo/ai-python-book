# Chapter 45 — Building the Backend with Claude Code: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## The Backend Build Loop › What to delegate, and what to keep

| **Delegate to Claude Code** | **Keep for yourself** |
|---|---|
| Boilerplate: serializers, URL wiring, admin registration, factories | **The data model.** A wrong table is the most expensive mistake to undo |
| First drafts of tests from your acceptance criteria | **The acceptance criteria** themselves: they are the product’s rules |
| Mechanical edits across many files | **Who may do what**: the permission matrix and the ownership rules |
| Explaining unfamiliar code and finding where something happens | **Anything touching money, secrets or personal data**: you review every line |
| A first security and bug review of a diff | **The decision to merge** |

> **The rule that keeps the backend yours**
>
> **You own the schema, the rules and the review; Claude Code writes the first draft of what is in between.** If you cannot explain a line it wrote, it does not go in.


## Schema First: From an ERD to Models and Migrations › The checker closes the loop

`erd_check` parses the ERD and reads `models.py` with Python’s `ast` module (no Django needed), then reports every difference: missing models and fields, type and `max_length` mismatches, wrong foreign-key targets and `on_delete` rules, missing unique, index and composite constraints, and wrong nullability. Against the reference models it is clean. Here it is against a **damaged copy** (a cascade turned into `SET_NULL`, a shortened title, a dropped unique, a missing index and a missing constraint), which is the kind of drift that appears when an AI "improves" a model:

**python core/review/erd_check.py (excerpt)**

```python
def compare(erd: dict[str, ErdModel], django: dict[str, DjangoModel]) -> list[Difference]:
    out: list[Difference] = []
    for name, em in erd.items():
        dm = django.get(name)
        if dm is None:
            out.append(Difference("error", name, "model is in the ERD but not in models.py"))
            continue
        for fname, ef in em.fields.items():
            df = dm.fields.get(fname)
            if df is None:
                out.append(Difference("error", name, f"field {fname} is missing"))
                continue
            if df.cls not in DJANGO_FOR[ef.kind]:
                out.append(Difference("error", name, f"{fname}: ERD says {ef.kind}, model has {df.cls}"))
                continue
            if ef.kind == "char" and ef.length and df.kwargs.get("max_length") != ef.length:
                out.append(Difference("error", name, f"{fname}: max_length is {df.kwargs.get('max_length')}, ERD says {ef.length}"))
            if ef.kind in ("fk", "one2one"):
                if ef.target and df.target and ef.target != df.target:
                    out.append(Difference("error", name, f"{fname}: points at {df.target}, ERD says {ef.target}"))
                if ef.on_delete and df.on_delete != ef.on_delete:
                    out.append(Difference("error", name, f"{fname}: on_delete is {df.on_delete or 'missing'}, ERD says {ef.on_delete}"))
                if ef.kind == "one2one" and df.cls != "OneToOneField":
                    out.append(Difference("error", name, f"{fname}: should be a OneToOneField"))
            if ef.unique and not (df.kwargs.get("unique") or df.cls == "OneToOneField"):
                out.append(Difference("error", name, f"{fname}: ERD says unique but the model allows duplicates"))
            fk_indexed = ef.kind in ("fk", "one2one") and df.kwargs.get("db_index", True) is not False
            if ef.index and not (df.kwargs.get("db_index") or df.kwargs.get("unique") or fk_indexed or any(c and c[0] == fname for c in dm.indexes)):
                out.append(Difference("warn", name, f"{fname}: ERD says indexed but there is no index"))
            if bool(df.kwargs.get("null")) != ef.null:
                out.append(Difference("error" if not ef.null else "warn", name,
                                      f"{fname}: null={bool(df.kwargs.get('null'))} but the ERD says {'nullable' if ef.null else 'required'}"))
        for cols in em.indexes:
            if _norm_cols(cols) not in {_norm_cols(c) for c in dm.indexes}:
                out.append(Difference("warn", name, f"missing index on ({', '.join(cols)})"))
        for cols in em.uniques:
            if _norm_cols(cols) not in {_norm_cols(c) for c in dm.uniques}:
                out.append(Difference("error", name, f"missing unique constraint on ({', '.join(cols)})"))
        for extra in sorted(set(dm.fields) - set(em.fields) - {"id"}):
            out.append(Difference("info", name, f"field {extra} is in the model but not in the ERD"))
    for extra in sorted(set(django) - set(erd)):
        out.append(Difference("info", extra, "model is in models.py but not in the ERD"))
    return out
```

**bash terminal (real output)**

```bash
$ python -m core.review.erd_check docs/erd.txt /tmp/bad_models.py
ERROR Conversation       public_id: ERD says unique but the model allows duplicates
ERROR Conversation       user: on_delete is set_null, ERD says cascade
ERROR Conversation       title: max_length is 100, ERD says 200
WARN  Message            created_at: ERD says indexed but there is no index
ERROR Message            missing unique constraint on (conversation, idempotency_key)

4 error(s), 1 warning(s), 0 note(s)
```

Give Claude this output and the instruction to fix it; it is a precise, objective instruction, much better than "check the models again".


## Schema First: From an ERD to Models and Migrations › Migrations: read them, do not trust them

A migration changes a live database, so it deserves the closest read of anything generated:

**bash terminal**

```bash
python manage.py makemigrations --check --dry-run     # fails if models and migrations disagree (run in CI)
python manage.py makemigrations conversations         # generate
python manage.py sqlmigrate conversations 0001        # READ the SQL it will run
python manage.py migrate                              # only on your development database
```

| **What AI often gets wrong in migrations** | **What to check** |
|---|---|
| **Editing an applied migration** instead of adding a new one | The rule in `CLAUDE.md`: never edit applied migrations; `git diff` shows only new files |
| **A destructive change without a plan** (dropping or renaming a column that holds data) | Rename with a `RenameField`; for removals, deploy code that stops using it first |
| **Adding a non-null column without a default** to a table with rows | Add it nullable, backfill in batches, then tighten |
| **A blocking index on a big table** | `AddIndexConcurrently` in a non-atomic migration (Chapter 40) |
| **Data migrations that call current model code** | Use `apps.get_model` inside `RunPython`, and give it a reverse function |
| **Two migrations with the same number** from two branches | `makemigrations --merge` |


## Write the Spec Before the Prompt

A spec is the answer to "what exactly should happen?". Writing it forces you to make the decisions Claude would otherwise make silently. Keep one short spec per feature in `docs/features/`, and point Claude at it with `@`. The template (`prompts/00_feature_spec_template.md`) has the same sections every time, so you never forget one:

| **Section** | **Why it is there** |
|---|---|
| **Goal** | One sentence a customer would understand. If you cannot write it, you are not ready to build |
| **Users and roles** | Who may do it, and who must **not** (Chapter 13’s roles) |
| **API contract** | Method, path, headers, request and response bodies, and **every status code** (Chapter 8). This is what the frontends will code against |
| **Data** | Only the changes to the ERD; whether it holds personal data and its retention rule (Chapter 34) |
| **Rules and edge cases** | Ownership, idempotency, limits, ordering, what happens when the AI provider fails |
| **Non-goals** | What **not** to build now. Without this, assistants gold-plate |
| **Security and privacy** | Which rule files apply; what must never be logged |
| **Acceptance criteria** | A numbered list of checkable statements. **Each becomes a test** |

Here is the template as it looks for the feature this chapter builds, sending a message and getting the AI’s reply (the placeholders in angle brackets are the parts you fill in, and the contract and acceptance criteria are already written for this feature):

**markdown prompts/00_feature_spec_template.md**

```markdown
# Feature spec: <name>

## Goal (one sentence a customer would understand)
<e.g. A signed-in user can send a message in one of their conversations and receive the AI's reply.>

## Users and roles
<who may do this; which roles from core/rbac.py; who must NOT be able to>

## API contract
- Method and path: `POST /api/v1/conversations/<public_id>/send/`
- Headers: `Authorization: Bearer ...`, `Idempotency-Key: <8-80 chars>`
- Request body: `{"content": "string, 1-8000 characters"}`
- Success: `201 {"public_id", "role", "content", "status", "ai_generated", "created_at"}`; `200` with the same body for a repeated key
- Errors: 400 validation, 401 not signed in, 403 role not allowed, 404 not found OR not yours, 429 throttled, 503 provider timeout (retry with the same key)

## Data (link to docs/erd.txt; list only changes)
<new models or fields, constraints, indexes, retention rule, whether personal data>

## Rules and edge cases
- <ownership, idempotency, limits, ordering, what happens on provider failure>

## Non-goals (what NOT to build now)
- <streaming, attachments, anything tempting but out of scope>

## Security and privacy
- <owner scoping, PII sent to the provider goes through core/responsible/pii.py, nothing sensitive in logs>

## Acceptance criteria (each one becomes a test)
1. Unauthenticated request returns 401.
2. Another user's conversation returns 404 and nothing is saved.
3. Empty or oversize content returns 400 and the provider is not called.
4. Same Idempotency-Key twice creates one user message and one reply.
5. A provider timeout returns 503; retrying with the same key succeeds without a second user message.
6. The list endpoint uses a constant number of queries.
```

Good acceptance criteria are **observable** ("returns 404 and nothing is saved") and **specific** ("one user message and one reply" for a repeated key). Vague ones ("handles errors gracefully") produce vague tests.


## Plan, Then Tests First › Red, green, refactor, with an assistant

1. **Red.** Claude writes tests that encode the acceptance criteria. Run them and **see them fail for the right reason** (a missing endpoint, not a typo). A test that passes before the code exists proves nothing.
2. **Green.** Claude writes the smallest implementation that passes. One layer at a time (service, then serializer and view).
3. **Refactor.** With green tests, ask for cleanups and run the tests again.
Two guardrails make this honest. **First, tests are not to be weakened.** An assistant under pressure to turn red into green will sometimes edit the test. The prompt forbids it, and your review checks it: `git diff` on the test files after the implementation step should show **no changed assertions** unless you agreed. **Second, think in mutations:** a good test fails when the code is wrong. After the tests pass, break the code on purpose (remove the owner filter, drop the idempotency check) and confirm that the matching test goes red. A test that stays green when the rule is broken is decoration.


## Services and Selectors: The Logic You Can Test Without a Database › The Django adapter and the selectors

The Django side is intentionally boring. The repository maps the service’s questions onto the ORM, and **every lookup is scoped to the owner**. The selectors hold the read queries and always take the user as an argument, so a forgotten filter is impossible:

**python reference/conversations/selectors.py**

```python
"""Read queries. Every function takes the user and scopes by it, so a forgotten filter is impossible."""
from django.db.models import Prefetch, QuerySet

from .models import Conversation, Message

def conversations_for(user) -> QuerySet[Conversation]:
    return Conversation.objects.filter(user=user, archived_at__isnull=True)

def conversation_list(user) -> QuerySet[Conversation]:
    """The list screen: one query for conversations plus one for each conversation's last message."""
    last = Message.objects.order_by("-created_at")
    return conversations_for(user).prefetch_related(Prefetch("messages", queryset=last[:1], to_attr="last_messages"))

def messages_for(user, conversation: Conversation) -> QuerySet[Message]:
    return Message.objects.filter(conversation=conversation, conversation__user=user, status__in=["ok", "pending"])
```

**python reference/conversations/services.py (excerpt)**

```python
class DjangoChatRepo:
    """Implements the ChatRepo protocol with the ORM. Every lookup is scoped to the owner."""

    def get_conversation(self, user_id, public_id):
        obj = Conversation.objects.filter(user_id=user_id, public_id=public_id, archived_at__isnull=True).first()
        return str(obj.pk) if obj else None

    def _to_stored(self, m: Message) -> StoredMessage:
        return StoredMessage(m.pk, str(m.conversation_id), m.role, m.content, m.status, m.idempotency_key)

    def find_by_key(self, conversation_id, key):
        m = Message.objects.filter(conversation_id=conversation_id, idempotency_key=key).first()
        return self._to_stored(m) if m else None

    def add(self, conversation_id, role, content, *, status="ok", key=None):
        try:
            with transaction.atomic():
                m = Message.objects.create(conversation_id=conversation_id, role=role, content=content, status=status, idempotency_key=key)
        except IntegrityError:                       # two requests raced on the same key: the database picked a winner
            m = Message.objects.get(conversation_id=conversation_id, idempotency_key=key)
        Conversation.objects.filter(pk=conversation_id).update(updated_at=timezone.now())      # bump the list order
        return self._to_stored(m)

    def history(self, conversation_id):
        return [self._to_stored(m) for m in Message.objects.filter(conversation_id=conversation_id).order_by("created_at", "id")]

    def reply_to(self, user_message_id):
        user_msg = Message.objects.get(pk=user_message_id)
        reply = (Message.objects.filter(conversation_id=user_msg.conversation_id, role="assistant", created_at__gte=user_msg.created_at)
                 .order_by("created_at", "id").first())
        return self._to_stored(reply) if reply else None

    def set_status(self, message_id, status):
        Message.objects.filter(pk=message_id).update(status=status)
```

Notice the `IntegrityError` handler in `add`: when two requests with the same key race, the **database’s** unique constraint picks one winner, and the loser reads the winner’s row. That is what "idempotency in the database" means, and it is why the constraint was in the ERD.


## The API Layer: Serializers, ViewSets, Permissions, Pagination, Throttling › OpenAPI documentation that stays true

Your web and mobile apps (and Claude Code itself, in the next chapters) will code against the API, so it needs a machine-readable description that is generated from the code and therefore cannot drift. `drf-spectacular` does that:

**python config/settings.py (additions)**

```python
INSTALLED_APPS += ["drf_spectacular"]
REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"] = "drf_spectacular.openapi.AutoSchema"
REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"] = "rest_framework.pagination.PageNumberPagination"
REST_FRAMEWORK["PAGE_SIZE"] = 20
SPECTACULAR_SETTINGS = {"TITLE": "AI Chat API", "VERSION": "1.0.0", "SERVE_INCLUDE_SCHEMA": False}
```

**python config/urls.py (additions)**

```python
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
```

**bash terminal**

```bash
python manage.py spectacular --file schema.yml --validate    # fails on schema errors and warnings you should fix
```

Add that command to CI so an endpoint that breaks the contract fails the build. Then give `schema.yml` to Claude Code when you build the frontends (`@schema.yml`): a precise contract beats a verbal description every time. Keep `/api/docs/` off, or behind authentication, in production unless you want a public map of your API.


## Authentication, Roles and RBAC Through Guided Prompts › The prompt

Prompt 3 asks for a **plan only** and names the exact deliverables (one permission class, the route-matrix test, tests for each role on each action, no role checks inside views). Authorization is the area where you should read every line Claude proposes, so ask for the plan, approve it, and then review the diff as a security change (45.8). Never accept "I added `if user.is_staff` checks where needed": that is the scattered-check design you are avoiding.

> **The most common AI authorization mistakes**
>
> Checking the role but not the **owner** (a member can read anyone’s conversation); returning **403** for an object that belongs to someone else (it confirms the object exists; use 404); trusting a **client-supplied** user id or role in the request body; permission checks only on the **list** endpoint and not on the detail or custom actions; and forgetting WebSocket consumers (45.6). The test class in 45.7 has one test for each.


## Celery Tasks, Channels Consumers and Payment Webhooks › Celery tasks (Chapter 15)

**python reference/conversations/tasks.py**

```python
import logging

from celery import shared_task

from core.chat.history import Message as HistoryMessage

from .models import Conversation, Message

logger = logging.getLogger(__name__)

@shared_task(autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, max_retries=3)
def generate_title(conversation_public_id: str) -> None:
    """Idempotent: running it twice leaves the same title. Queue it with transaction.on_commit (Chapter 15)."""
    conversation = Conversation.objects.filter(public_id=conversation_public_id).first()
    if conversation is None or conversation.title:
        return                                                   # nothing to do, or already titled: safe to repeat
    first = Message.objects.filter(conversation=conversation, role="user").order_by("created_at").first()
    if first is None:
        return
    title = " ".join(first.content.split())[:60]
    Conversation.objects.filter(pk=conversation.pk, title="").update(title=title)      # only if still empty: no overwrite race
    logger.info("title generated", extra={"event": "title_generated", "fields": {"conversation": conversation_public_id}})
```

Review for these:

- **Idempotent.** Running the task twice leaves the same result. Here the title is only set if it is still empty, in one `UPDATE ... WHERE title = ''`, so a retry or a duplicate delivery changes nothing.
- **Arguments are ids and strings,** never model instances (they do not serialize, and they go stale).
- **Queued after the commit** (`transaction.on_commit(lambda: generate_title.delay(...))`) so the worker never looks for a row that does not exist yet (Chapter 40).
- **Retries only for transient errors,** with backoff and a cap. Retrying a validation error forever is a loop.
- **No message text in logs;** the conversation’s public id and the task id are enough.

## Reviewing AI-Generated Backend Code › A first reviewer you run in a second

`django_review` reads Python source with the standard library’s `ast` module and flags the mechanical patterns above in under a second, offline, with no Django installed. Here is a deliberately bad "first draft" of the kind an assistant produces when asked for a stats endpoint and a notification helper with no constraints (it is `bad_example/views.py` in the repository), and the real report:

**python bad_example/views.py**

```python
# A typical first draft: it works in the demo and fails every review.
import random
import requests
from datetime import datetime
from rest_framework import serializers, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import connection

PAYSTACK_SECRET_KEY = "sk_live_51HqexampleKEYabcdef"

class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = "__all__"

class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer

    def get_queryset(self):
        return Conversation.objects.all()

class StatsView(APIView):
    def get(self, request):
        convs = Conversation.objects.filter(archived_at=None)
        rows = []
        for c in convs:
            last = Message.objects.filter(conversation=c).last()
            rows.append({"id": c.id, "last": last.content if last else None})
        print("stats built", rows)
        return Response(rows)

def search(request):
    q = request.GET.get("q", "")
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM conversations_conversation WHERE title LIKE '%{q}%'")
        return cursor.fetchall()

def make_reset_token():
    return str(random.randint(100000, 999999))

def notify(user, text, tags=[]):
    try:
        requests.post("https://hooks.example.com/notify", json={"text": text})
    except:
        pass
    tags.append(user.id)
    user.last_notified = datetime.now()
    user.save()
    Audit.objects.create(user=user, kind="notify")
```

**bash terminal (real output)**

```bash
$ python -m core.review.django_review bad_example
bad_example/views.py
  line 10   ERROR DJ013  PAYSTACK_SECRET_KEY is assigned a string literal: read secrets from the environment
  line 16   ERROR DJ001  fields = '__all__' exposes (and accepts) every column; list the fields explicitly
  line 19   WARN  DJ015  ConversationViewSet sets no permission_classes: confirm the global default is deny-by-default
  line 23   WARN  DJ003  get_queryset: .objects.all() in a view with no user scoping; filter by request.user
  line 26   WARN  DJ015  StatsView sets no permission_classes: confirm the global default is deny-by-default
  line 31   WARN  DJ024  database query inside a loop: possible N+1; use select_related, prefetch_related or one query
  line 33   WARN  DJ009  print() in application code: use logging (and never log secrets or message text)
  line 40   ERROR DJ005  execute() with an interpolated string: SQL injection. Pass parameters separately
  line 45   ERROR DJ010  random.randint is predictable; use the secrets module for tokens and codes (in make_reset_token)
  line 48   ERROR DJ007  mutable default argument is shared between calls; default to None
  line 48   WARN  DJ020  notify makes 2 database writes without transaction.atomic
  line 50   WARN  DJ012  requests.post() has no timeout: a slow server would hang a worker
  line 51   ERROR DJ006  bare except: catches KeyboardInterrupt and hides every bug
  line 54   WARN  DJ008  datetime.now() is naive: use django.utils.timezone.now() (time zone aware)

6 error(s), 8 warning(s) in 1 file(s)
```

Fourteen findings in 56 lines. Paste this report back to Claude Code with "fix each finding; run the tests; show the diff" and you have turned a vague review into a precise instruction. The reference app, run through the same tool, reports nothing.

The rule table the tool applies (the codes in the output):

| **Code** | **Finds** | **Level** |
|---|---|---|
| **DJ001, DJ002** | `fields = "__all__"`, serializer `exclude` | error, warn |
| **DJ003, DJ015, DJ016** | Unscoped `objects.all()` in a view; no `permission_classes`; `AllowAny` | warn |
| **DJ005** | SQL built by f-string, `%`, `+` or `.format` | error |
| **DJ006, DJ007** | Bare `except`, swallowed `Exception`; mutable default arguments | error, warn |
| **DJ008, DJ009, DJ012** | Naive `datetime.now()`; `print`; `requests` without timeout | warn |
| **DJ010, DJ011, DJ013** | Weak randomness for tokens; `eval`, `exec`, `pickle`; hardcoded secrets | error |
| **DJ014, DJ017, DJ018** | `FloatField` for money; `DEBUG = True`; `ALLOWED_HOSTS = ["*"]` | error, warn |
| **DJ020, DJ024** | Several writes with no transaction; query inside a loop | warn |
| **DJ027, DJ028** | `shell=True`; `verify=False` | error |

> **What a static reviewer cannot see**
>
> It reads code, it does not run it. It cannot tell whether a filter is the **right** filter, whether a permission matrix is correct, whether a test would fail if the code were wrong, or whether a function invents an API that does not exist. It is the first layer of the funnel above, not the last. Treat a clean report as "no known mechanical mistakes", never as "safe".


## When the Result Is Wrong

Sooner or later Claude Code will produce something wrong, and what you do next decides whether you lose five minutes or an afternoon.

- **Do not pile prompts on a broken result.** Each "no, fix it" adds confusing context. If the second attempt is also wrong, the problem is the **first** prompt.
- **Go back one step.** Use `/rewind` (Esc Esc) or `git restore` (Chapter 43) to return to the last good state, then restate the request **smaller and clearer**.
- **Diagnose before you ask for a fix.** "Why does `test_other_user_gets_404` fail? Explain, do not change code." The explanation tells you whether Claude understands the problem.
- **Give it the evidence, not your conclusion.** Paste the failing test output or the checker report. "Fix the 4 errors from `erd_check`" beats "the models look wrong".
- **Ask for options** when the design is uncertain: "give me two ways to do idempotency, with trade-offs, no code yet". You choose; then it builds.
- **Make the next step smaller.** One service function, then its view, then its test. Big prompts produce big, tangled mistakes.
- **Start a fresh session** when the conversation is long and confused (`/clear`), and restate the goal with the spec attached.
- **Take over by hand** when it is faster. A one-line fix is quicker to type than to explain. The goal is a correct backend, not a record number of prompts.
- **Capture the lesson.** If Claude repeats a mistake (for example, forgetting owner scoping), add one concrete sentence to the backend rules so the next session starts wiser.

## Keep the Context Small: Work in Slices, Leave Notes

A backend has dozens of files, and a single long conversation about all of them degrades quickly (Chapter 43 explained why). Three habits keep each session sharp:

1. **One slice per session,** ending with a commit and `/clear`. "Models for conversations" is one session; "send-message API" is the next; "Celery title task" is the third.
2. **Put decisions in files, not in the chat.** The ERD, the feature spec and `CLAUDE.md` outlive any session. When a session decides something (a status code, a naming rule), ask Claude to write it into the spec or the rules file and commit it. The next session reads it for free.
3. **Point, do not paste.**  `@docs/features/send-message.md`, `@backend/conversations/services.py`, `@schema.yml`. The files stay current; pasted text goes stale.
A short `docs/features/` folder, one file per feature (goal, contract, rules, acceptance criteria), doubles as your documentation and your regression checklist.
