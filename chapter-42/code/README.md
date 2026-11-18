# Chapter 42 code: Code Quality and CI

Copy these into the root of your monorepo (`backend/`, `web/`, `mobile/` side by side) and adjust names and paths.

- `.github/workflows/ci.yml`: the pull-request pipeline (changes, workflow lint, backend, web, mobile, one gate).
- `.github/workflows/security.yml`: scheduled dependency audits.
- `.github/dependabot.yml`, `.github/CODEOWNERS`: automatic updates and required reviewers.
- `ci/`: `changed_areas.py`, `gate.py` and their 13 tests (`python ci/test_ci_scripts.py`), `install_actionlint.sh` (pinned and checksummed), `ruff.toml`.
- `backend/pyproject.toml`: Ruff, mypy (with django-stubs), coverage. The list of test modules in the mypy section is Chapter 32's: replace it with yours.
- `backend/requirements.txt`, `backend/requirements-dev.txt`: fully pinned. Production and tooling are separate on purpose.
- `.pre-commit-config.yaml`: fast hooks, pinned.
- `mobile/` and `web/`: ESLint (flat config), Prettier and the `package.json` scripts and versions to add (`package.scripts.json`).
- `fixes-from-chapter-32/`: `backend.patch` and `mobile.patch`, the real changes the tools led to in the Chapter 32 code. They apply cleanly to the Chapter 32 download (`git apply`) and reproduce the tree that was verified.

Look up the current commit SHAs of the GitHub Actions with `git ls-remote` before you copy the workflows.

Verified (November 2026): Ruff 0.17.4, mypy 2.4.1, django-stubs 6.1.2, coverage 7.17.2, Django 6.1.3 tests on SQLite and PostgreSQL 16.15, Prettier 3.9.10, ESLint 9 (Expo) and 10 (Next.js, scratch project), TypeScript 6.0.3 and 7.0.2, pre-commit 4.7.0, actionlint 1.7.12, zizmor 1.32.0.
Not verified: execution on GitHub itself.
