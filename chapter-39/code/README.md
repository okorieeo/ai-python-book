# Chapter 39 code: Testing Strategies

    backend/billing/         webhook core (signatures, idempotency, endpoint decisions, handlers)  framework-free, TESTED
    backend/testsupport/     signing helpers, fake clock, network blocker                          TESTED
    backend/scripts/         send_webhook.py: send a correctly signed webhook to any URL           TESTED (real HTTP)
    backend/tests/           97 pytest-style tests for all of the above, incl. a real HTTP round trip
    backend/tools/           mutation_demo.py: breaks the code 16 ways and checks the tests notice
    backend/billing/{models,stores,views}.py, backend/urls.py, backend/tests_django/, backend/pytest.ini
                             Django, Celery and Channels layers and tests                          NOT RUN here
    web/lib/                 formatMoney, entitlements, checkout polling + 36 Jest-style tests     TESTED
    web/e2e/                 Playwright spec (5 tests) + a stand-in app it runs against            TESTED in real Chromium
    web/components, jest.config.ts, playwright.config.ts, e2e/auth.setup.ts                        NOT RUN here
    mobile/                  jest-expo + RNTL tests, Maestro flows, EAS workflow                   NOT RUN here
    .github/workflows/tests.yml
    verification_only/       STAND-INS for pytest, Jest and @playwright/test that were used to run the tests in a
                             sandbox with no network. NOT for your project: use the real tools.

## Run (with the real tools, in your project)

    cd backend && pip install pytest pytest-django pytest-asyncio pytest-xdist pytest-cov && pytest
    cd web && npm i -D jest jest-environment-jsdom @testing-library/react @testing-library/dom @testing-library/jest-dom \
        @testing-library/user-event @playwright/test ts-node @types/jest && npx jest && npx playwright test
    cd mobile && npx expo install jest-expo jest @types/jest --dev && npm i -D @testing-library/react-native && npx jest

The framework-free backend tests need no Django. To run the Python tests the way they were verified here:

    python verification_only/mini_pytest.py backend/tests
    cd backend && python tools/mutation_demo.py --runner "python ../verification_only/mini_pytest.py tests"   # (absolute path in a temp dir)
    tsx --import ./verification_only/jest-globals.mjs --test web/lib/*.test.ts
    tsx verification_only/run-e2e.mjs web/e2e/checkout.spec.ts
