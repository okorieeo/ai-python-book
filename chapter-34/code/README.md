# Chapter 34 code: Responsible AI

Extends the Chapter 17 project. Needs Chapter 17's `core/security/redaction.py` and `audit` app.

    core/responsible/   plain Python, no Django:  pii, consent_logic, retention, erasure, export,
                        citations, safety, bias, data_inventory
    core/test_responsible.py   66 unittest tests: python -m unittest core.test_responsible -v
    privacy/            Django app: consent events, legal documents, export, deletion, Celery tasks
    chat/ai_pipeline.py        redaction + safety around the model call
    chat/test_ai_pipeline.py, privacy/tests.py    Django tests (need Django, DRF, PostgreSQL)
    legal/              Terms, Privacy Policy, AI system card, DPIA templates (not legal advice)

Add "privacy" to INSTALLED_APPS, include privacy.urls under /api/v1/privacy/, and set in settings:
SAFETY_SUPPORT_MESSAGE, PROMPT_CANARY (from the environment), and
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"privacy_export": "3/hour", "privacy_delete": "3/day"}.
