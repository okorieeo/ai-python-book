# Chapter 58 code: Project 3, Smart Farm / IoT Monitoring with AI Insights (FarmSense)

```
chapter_58_code/
  farmsense_core/   plain Python, fully tested: sensor validation, batch ingestion rules, device keys, aggregation, the alert engine,
                    roles and permissions, daily reports (text and PDF), AI-insight guardrails, partitions, simulator, replay
  farmsense/        the Django app: models, ingestion endpoint, Celery tasks, WebSocket consumer, REST views, Expo push,
                    isolation tests.  NOT run in the book's environment
  frontend/         Next.js (TypeScript): live dashboard hook, sensor tile, alert list, insight card
  mobile/           Expo (React Native): push registration, alerts screen
  scripts/          simulate_device.py: a fake sensor you can point at your own server
  tests/            65 tests
```

## What was and was not executed

- **Run and passing:** everything in `farmsense_core/`, the fake-device script's payloads, and the replay scenario (65 tests, plus a real PDF report).
- **Syntax-checked only:** `farmsense/*.py` (compiled) and the TypeScript in `frontend/` and `mobile/` (parsed, not type-checked).
  PostgreSQL, Django, Celery, Redis, Channels, a phone and API keys were not available. The Django isolation tests are written but not run.

## Try it without a server

```bash
pip install pypdf reportlab                      # reportlab renders the PDF report; pypdf is used by the tests
python3 -m unittest discover -s tests -t . -v
python3 -m farmsense_core.replay                 # the three-day alert scenario
```

## Use it in your project

1. Copy `farmsense_core/` and `farmsense/` into your Django project; install `celery channels djangorestframework requests anthropic reportlab`.
2. Add `farmsense` to INSTALLED_APPS, the settings from `farmsense/settings_snippet.py`, include `farmsense.urls`, and add `farmsense/routing.py` to your ASGI routes.
3. `python manage.py makemigrations farmsense` (creates `0001_initial`), then `migrate` (the hand-written `0002_readings.py` creates the partitioned table).
4. Run three processes: `celery -A config worker -Q alerts`, `celery -A config worker -Q celery`, `celery -A config beat`.
5. In the Django shell create a Farm, a Site, a Device (with `farmsense_core.devices.generate_device_key()`; save the key id and hash, keep the full key) and a Sensor, then run `scripts/simulate_device.py` against `/api/ingest/`.
6. Copy `frontend/` into your Next.js app and `mobile/` into your Expo app (push needs a development build and an EAS project id).
