# Chapter 29 code: Integrating LLMs into Django

    ai/dto.py                 plain data: messages, usage, events           (pure, no Django)
    ai/errors.py              our errors; the SDK never leaks past the adapter
    ai/provider_errors.py     HTTP status -> our error                       (tested)
    ai/pricing.py             integer micro-dollar cost                      (tested)
    ai/context.py             history planning, summary budget, alternation  (tested)
    ai/resilience.py          circuit breaker, concurrency cap, fallback     (tested)
    ai/sse.py                 Server-Sent Events framing + heartbeat         (tested)
    ai/service.py             ChatService: the one place AI calls happen     (tested)
    ai/summarizer.py          rolling summary ("memory")                     (tested)
    ai/testing.py             FakeLLM used by the tests
    ai/anthropic_client.py    the ONLY file that imports the Anthropic SDK   (not run: SDK not installed)
    ai/models.py store.py budget.py factory.py tasks.py views.py reports.py  Django layer (not run: Django not installed)
    core/async_auth.py        auth + throttle for a plain async view
    ai/test_views.py          Django tests (run in your project)

Run the offline tests (Python 3.11+, nothing to install):

    python -m unittest discover -s . -p "test_*.py" -t .    # from this folder; skips test_views.py if Django is missing

Wire-up: add `path("api/v1/", include("ai.urls"))`, `"ai"` to INSTALLED_APPS, the lines from
ai/settings_snippet.py, `pip install anthropic`, add the three Message fields and Conversation.summary
shown at the bottom of ai/models.py, run makemigrations/migrate, and serve with ASGI (uvicorn or daphne).
