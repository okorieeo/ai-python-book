# Chapter 56 code: AI Chat Assistant SaaS

backend/   Django + Channels + Celery (accounts, chat, billing, ai)
clients/   shared TypeScript (protocol, reducer, socket client, hook), web/ (Next.js), mobile/ (Expo)

Backend:  cd backend && pip install -r requirements.txt && export DJANGO_DEBUG=1
          python manage.py migrate && daphne config.asgi:application
Tests:    python manage.py test --settings=config.settings_test        (88 tests)
Clients:  cd clients && npm install && npm run typecheck && npm test   (12 tests)
