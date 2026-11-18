"""Create the folder structure for a new full-stack AI product (monorepo)."""
import sys
from pathlib import Path

NAME = sys.argv[1] if len(sys.argv) > 1 else "ai-chat-app"
root = Path(NAME)

FILES = {
    "README.md": f"""# {NAME}

One-sentence description of the product and who it is for.

## Structure
- `backend/`  Django REST API, Channels (WebSockets), Celery
- `web/`      Next.js web app
- `mobile/`   React Native (Expo) app
- `docs/`     Product brief, user stories, architecture, decisions (ADRs), UX
- `deploy/`   Docker and Dokploy configuration

## Run locally
See `docs/development.md` (to be written as you build).
""",
    ".gitignore": ".venv/\n__pycache__/\n*.pyc\nnode_modules/\n.next/\ndist/\n.expo/\n.env\n.env.*\n!.env.example\n.DS_Store\n*.log\n",
    ".env.example": "# Copy to .env and fill in real values. NEVER commit .env\nDJANGO_SECRET_KEY=change-me\nDJANGO_DEBUG=true\nDATABASE_URL=postgres://app:app_password@localhost:5432/app_db\nREDIS_URL=redis://localhost:6379/0\nANTHROPIC_API_KEY=\nSTRIPE_SECRET_KEY=\nSTRIPE_WEBHOOK_SECRET=\nPAYSTACK_SECRET_KEY=\n",
    "docs/product-brief.md": "# Product brief\n\n## Problem\n\n## Target users (persona)\n\n## Solution in one paragraph\n\n## MVP scope (must have)\n\n## Not in the MVP\n\n## Success metrics\n",
    "docs/user-stories.md": "# User stories\n\n## Epic: Accounts\n- [ ] As a visitor, I want to sign up with my email so that I can start using the app.\n  - Given a valid email and password, when I submit, then I receive a verification email.\n",
    "docs/decisions/0000-template.md": "# ADR-0000: Title\n\nStatus: Proposed | Accepted | Superseded\nDate:\n\n## Context\n\n## Decision\n\n## Alternatives considered\n\n## Consequences\n",
    ".github/PULL_REQUEST_TEMPLATE.md": "## What changed and why\n\n## How I tested it\n\n## Checklist\n- [ ] Tests added or updated\n- [ ] No secrets or .env files committed\n- [ ] Docs / OpenAPI updated if the API changed\n- [ ] Screenshots for UI changes\n",
    "deploy/.gitkeep": "",
    "backend/.gitkeep": "",
    "web/.gitkeep": "",
    "mobile/.gitkeep": "",
}

for relative, content in FILES.items():
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

print(f"Created {NAME}/")
for path in sorted(root.rglob("*")):
    depth = len(path.relative_to(root).parts)
    print("  " * depth + path.name + ("/" if path.is_dir() else ""))
