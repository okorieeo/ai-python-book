# Chapter 57 code: Project 2, Document Q&A (RAG) Platform

```
chapter_57_code/
  docuask_core/     plain Python, fully tested: text cleanup, extraction (PDF, Word, text), chunking, embeddings interface,
                    retrieval ranking, prompt and citation handling, usage limits, evaluation harness
  docuask/          the Django app: models, Celery ingestion, hybrid search, LLM calls, REST views, WebSocket consumer,
                    usage counters, health endpoints, tenant-isolation tests.  NOT run in the book's environment
  frontend/         Next.js (TypeScript) components: upload, document list polling, streaming ask panel, usage meter
  tests/            51 tests + a small sample corpus and 25 evaluation questions
```

## What was and was not executed

- **Run and passing:** everything in `docuask_core/` and `tests/` (51 tests), including real PDF and Word files made on the fly,
  a zip bomb, an encrypted PDF, 50 simultaneous quota requests, and the evaluation harness.
- **Syntax-checked only:** `docuask/*.py` (compiled with Python) and `frontend/*.ts(x)` (parsed with the TypeScript compiler, not type-checked).
  They need Django, PostgreSQL with pgvector, Celery, Redis, API keys and Node packages that were not available.
- Read each of these files and run them on your own machine before you rely on them.

## Run the tests and the evaluation (no database, no API key)

```bash
pip install pypdf python-docx reportlab          # reportlab is only used by the tests, to create sample PDFs
python3 -m unittest discover -s tests -t . -v
python3 -m docuask_core.evals
```

## Use it in your project

1. Copy `docuask_core/` and `docuask/` into your Django project; add `django.contrib.postgres` and `docuask` to INSTALLED_APPS.
2. `pip install pgvector voyageai anthropic celery channels djangorestframework`
3. Use a PostgreSQL image with pgvector (for example `pgvector/pgvector:0.8.2-pg17`; check Docker Hub for current tags).
4. `python manage.py makemigrations docuask && python manage.py migrate` (the enable-extension migration must run first).
5. Add the settings from `docuask/settings_snippet.py`, include `docuask.urls`, and add `docuask/routing.py` to your ASGI routes.
6. Copy `health_checks.py` from Chapter 54's code if the copy here is missing, and run a worker: `celery -A config worker -Q ingest,celery -l info`.
7. Copy `frontend/` into your Next.js app.
