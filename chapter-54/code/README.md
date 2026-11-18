# Chapter 54 code: Deploying with Dokploy

```
chapter_54_code/
  deploy/docker-compose.prod.yml     the app services for Dokploy (databases are created in Dokploy, not here)
  deploy/.env.production.example     every variable the compose file needs, with placeholders only
  .github/workflows/deploy.yml       test -> ask Dokploy to deploy -> smoke test the live site
  dokploycheck/                      compose linter (python -m dokploycheck) and smoke test (python -m dokploycheck.smoke)
  backend_snippets/                  health_checks.py (tested) and health_views.py (Django wrapper, NOT run: Django was unavailable)
  runbooks/                          rollback.md and restore-drill.md
  tests/                             29 tests and the "bad" fixtures used in the chapter
```

Python 3.10+; the only dependency is PyYAML (`pip install pyyaml`).

```bash
python3 -m unittest discover -s tests -t . -v                                  # run the tests
python3 -m dokploycheck deploy/docker-compose.prod.yml --env-example deploy/.env.production.example
python3 -m dokploycheck tests/fixtures/bad/docker-compose.bad.yml --env-example tests/fixtures/bad/env.bad.example   # see it fail
python3 -m dokploycheck.smoke --app https://app.example.com --api https://api.example.com --wait 600
```

Copy `dokploycheck/` and `backend_snippets/` into your repository (the workflow expects `dokploycheck/` at the repo root).
Adjust build contexts, the Django project name (`config`) and the commands in the compose file to match your Chapter 51 and 52 setup.
