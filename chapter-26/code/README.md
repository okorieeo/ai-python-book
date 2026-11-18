# Chapter 26 code: Building and Releasing Mobile Apps

    mobile/eas.json                    build + submit profiles
    mobile/app.config.ts               identity per variant (APP_VARIANT)
    mobile/config/variants.ts          the three variants (pure, tested)
    mobile/scripts/checkRelease.ts     25 release rules (pure, tested)
    mobile/scripts/release-check.ts    CLI: npm run release:check
    mobile/src/release/*               version gate, update banner, release info
    mobile/src/privacy/AiConsentGate   Apple 5.1.2(i) consent screen
    backend/core/app_config/*          GET /api/v1/app-config/ (version gate)
    .github/workflows/mobile-*.yml     checks, tag build, preview updates
    store/*                            review notes + data declaration worksheet

Merge the "scripts" and "devDependencies" from mobile/package.scripts.json into your package.json.
Add `path("api/v1/", include("core.app_config.urls"))` to config/urls.py and
`"app_config": "60/min"` to DEFAULT_THROTTLE_RATES.

Tests:   cd mobile && npm run test:release        (50 tests)
         cd backend && python -m unittest core.app_config.test_version_gate   (11 tests)
         cd backend && python manage.py test core.app_config.test_views       (needs Django)
