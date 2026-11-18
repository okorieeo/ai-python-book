# Chapter 59 code: AI Productivity Assistant

Copy each folder into your project at the same path (see section 59.19 of the chapter).

    backend/                 Django project files (apps: tasks, schedule, assistant, plus core/ and evals/)
      core/                  timeutils.py, api_fields.py  (+ test_timeutils.py)
      schedule/              models, recurrence.py, availability.py, services, serializers, views (+ tests)
      tasks/                 models, planning.py, services, serializers, views (+ test_planning.py, test_api.py)
      assistant/             tools.py, agent.py, history.py, prompt.py, untrusted.py, briefing.py   (pure Python)
                             toolset.py, models.py, services.py, anthropic_client.py, views.py,
                             consumers.py, notify.py, tasks.py                                      (Django)
      evals/                 harness.py, cases.py, run_live.py (+ test_harness.py)
      config_snippets/       settings, urls/routing and audit-action additions to merge by hand
    packages/shared/         assistant-protocol.ts, calendar-layout.ts, useAssistant.ts (+ tests)
    web/                     Next.js components and the Today page
    mobile/                  Expo assistant screen and push registration
    verification/            the scripts used to check the code while the chapter was written (see below)

## Run the tests that need no Django

From `backend/` (Python 3.12 or later; it also needs the Chapter 17 `core/security` and `audit` code on the path):

    python -m unittest core.test_timeutils schedule.test_recurrence schedule.test_availability \
        tasks.test_planning assistant.test_untrusted assistant.test_tools assistant.test_agent \
        assistant.test_prompt_briefing assistant.test_history evals.test_harness
    # expected: Ran 168 tests ... OK

From `packages/shared/` (Node 22 recent enough to run TypeScript directly; the author used 22.23):

    node --test "src/*.test.ts"      # expected: tests 24, pass 24
    npx tsc --noEmit                 # needs `npm install` for @types/node and @types/react first

## What was and was not run

Run and passing: everything listed above, plus `assistant/test_toolset_schemas.py` (5 tests, with the Django
modules stubbed), 15 deliberate-bug mutation checks (15 caught) and 7 TypeScript mutations (6 caught, 1 equivalent).

NOT run: Django, DRF, Channels, Celery and the Anthropic SDK were not installable, so models, services, views,
consumer, Celery tasks, the Anthropic adapter, `assistant/test_services.py` and `tasks/test_api.py` were only
syntax-checked. The Next.js and Expo screens were not run in a browser or on a device. The live model was never
called, so `evals/run_live.py` has never been executed. Run these in your project and trust what you see.

`verification/` holds the author's scripts (they contain the author's absolute paths: edit before use).
