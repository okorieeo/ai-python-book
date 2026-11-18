# Chapter 45 code: Building the Backend with Claude Code

    core/chat/            framework-free chat use case: ChatService, trim_history, in-memory repo and fake providers
    core/rbac.py          roles, permission matrix, deny-by-default can(), matrix_gaps(), unused_actions()
    core/review/          django_review.py (ast reviewer for AI-generated Django code), erd_check.py (ERD vs models.py)
    docs/erd.txt          the ERD for the conversations app (the source of truth you give Claude Code)
    prompts/              the seven prompt templates used in the chapter (spec, models, API, RBAC, tasks, tests, review)
    .claude_rules_backend.md   place at .claude/rules/backend.md
    reference/conversations/   a reference Django app (models, selectors, services, views, permissions, tasks, consumer, tests)
    bad_example/views.py  a deliberately bad "first draft" used to demonstrate the reviewer (do not copy it)

Tests (72):  python -m unittest core.chat.test_chat core.review.test_django_review core.review.test_erd_rbac -v
Reviewer:    python -m core.review.django_review backend/          (exit status 1 on errors)
ERD check:   python -m core.review.erd_check docs/erd.txt backend/conversations/models.py

The reference Django app was syntax-checked only (Django, DRF, Celery and Channels were not installed).
Assumes the User model of Chapter 13 has public_id and role, and settings.CHAT_PROVIDER names your provider class (Chapter 29).
