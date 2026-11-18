"""Review NEW dependencies in a diff before you accept them. Offline: it reads only the diff.

Usage:  git diff main...HEAD | python -m tools.dep_review

Why: AI assistants sometimes suggest packages that do not exist, or whose names are one typo away from a
popular one. Attackers register such names ("slopsquatting", "typosquatting"). This script flags names that are
CLOSE to a well-known package, unpinned versions, and packages installed from a URL. It does NOT check
that a package is safe. Verify every new dependency yourself (see the checklist printed at the end).
"""
from __future__ import annotations

import re
import sys

POPULAR_PYPI = """requests django djangorestframework celery redis psycopg2 psycopg gunicorn uvicorn daphne channels channels-redis
numpy pandas scipy flask fastapi pydantic sqlalchemy alembic boto3 pytest pytest-django coverage black ruff flake8 mypy pillow
cryptography pyjwt urllib3 certifi setuptools wheel pip click jinja2 markupsafe werkzeug httpx aiohttp anthropic openai stripe
django-cors-headers django-environ django-filter whitenoise sentry-sdk python-dotenv pyyaml lxml beautifulsoup4 tqdm rich
typing-extensions packaging attrs python-dateutil pytz tzdata orjson openpyxl django-storages drf-spectacular""".split()
POPULAR_NPM = """react react-dom next typescript express lodash axios webpack vite eslint prettier jest vitest tailwindcss
postcss autoprefixer zod react-native expo expo-router expo-secure-store openapi-fetch openapi-typescript dotenv uuid moment
dayjs date-fns chalk commander debug jsonwebtoken bcrypt cors body-parser mongoose redis socket.io socket.io-client
styled-components framer-motion swr zustand redux react-redux rxjs tslib core-js ws node-fetch next-auth stripe openai
@anthropic-ai/sdk @types/node @types/react @types/react-dom @testing-library/react @testing-library/jest-dom
@testing-library/user-event @tanstack/react-query eslint-config-next""".split()

VERSION_LIKE = re.compile(r"^(\^|~|>=?|<=?|=|\*|latest$|next$|\d|git\+|git:|github:|https?:|file:|link:|workspace:|npm:)")
NPM_LINE = re.compile(r'^\s*"(@?[A-Za-z0-9._~/-]+)"\s*:\s*"([^"]*)"\s*,?\s*$')
REQ_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*(==|>=|<=|~=|!=|>|<|===)?\s*([^\s;#]*)")
NPM_NONDEPS = {"name", "version", "description", "main", "type", "private", "license", "author", "homepage", "repository", "types"}


def norm_py(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def edit_distance(a: str, b: str) -> int:
    """Edit distance where swapping two neighbouring letters (lodahs/lodash) counts as ONE edit."""
    if abs(len(a) - len(b)) > 3:
        return 99
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def lookalike(name: str, popular: list[str]) -> str | None:
    if name in popular or len(name) < 5:
        return None
    best = min(popular, key=lambda p: edit_distance(name, p))
    d = edit_distance(name, best)
    return best if d <= (1 if len(name) < 8 else 2) else None


def parse_added_deps(diff_text: str) -> list[tuple[str, str, str, str]]:
    """Return (ecosystem, file, name, version_spec) for every dependency line ADDED in the diff."""
    out, current = [], ""
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            current = raw[4:].strip()
            current = current[2:] if current.startswith("b/") else current
            continue
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        line = raw[1:]
        base = current.rsplit("/", 1)[-1]
        if base == "package.json":
            m = NPM_LINE.match(line)
            if m and m.group(1) not in NPM_NONDEPS and VERSION_LIKE.match(m.group(2)):
                out.append(("npm", current, m.group(1), m.group(2)))
        elif base.startswith("requirements") and base.endswith(".txt"):
            if line.strip().startswith(("#", "-")) or not line.strip():
                if line.strip().startswith(("-e", "git+")):
                    out.append(("pypi", current, line.strip(), "url"))
                continue
            m = REQ_LINE.match(line)
            if m:
                out.append(("pypi", current, m.group(1), (m.group(3) or "") + (m.group(4) or "")))
    return out


def review(diff_text: str) -> list[str]:
    notes = []
    for eco, file, name, spec in parse_added_deps(diff_text):
        label = f"{file}: {name} {spec}".strip()
        if spec == "url" or re.match(r"^(git\+|git:|github:|https?:|file:|link:)", spec):
            notes.append(f"WARNING {label}: installed from a URL or git, not the package registry")
        if eco == "pypi":
            if spec != "url" and (spec == "" or not spec.startswith(("==", "===", "~="))):
                notes.append(f"WARNING {label}: not pinned exactly (use == and a lockfile with hashes if you can)")
            twin = lookalike(norm_py(name), POPULAR_PYPI)
        else:
            if spec in ("*", "latest", "next") or spec.startswith((">", "<")):
                notes.append(f"WARNING {label}: unpinned range; commit the lockfile and prefer exact or caret versions")
            twin = lookalike(name.lower(), POPULAR_NPM)
        if twin:
            notes.append(f"ERROR   {label}: name is very close to popular package '{twin}'. Typo, or a lookalike?")
        notes.append(f"NEW     {eco} package '{name}': verify it exists, who maintains it and when it was published")
    return notes


CHECKLIST = """Before accepting a new dependency:
  1. Does the package really exist in the registry, under exactly this name?  (npm view <name> / the PyPI page)
  2. Is it what you meant? Compare with the official docs or repository of the library you wanted.
  3. Age, maintainers, recent releases, download count, license, open security advisories.
  4. Do you need it at all? Could the standard library or an existing dependency do the job?
  5. Is the version pinned and the lockfile committed? Does the install run scripts?"""


def main(argv: list[str]) -> int:
    notes = review(sys.stdin.read())
    if not notes:
        print("dependency review: no new dependencies in this diff")
        return 0
    print("\n".join(notes))
    print("\n" + CHECKLIST)
    return 1 if any(n.startswith("ERROR") for n in notes) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
