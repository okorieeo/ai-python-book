# Chapter 52 code: Docker Compose for Full-Stack Apps

Unzip into the root of the AI Chat project (next to `backend/` and `frontend/`).
It adds to the Chapter 51 files; `backend/Dockerfile` REPLACES Chapter 51's (it only adds
the `/app/media` lines described in section 52.5).

| File | Purpose |
|---|---|
| `compose.yaml` | The shared base: all services, no published ports |
| `compose.dev.yaml` | Development overlay: localhost ports, code mounted, debug on |
| `compose.prod.yaml` | Production overlay: restart, log rotation, hardening, memory limits |
| `compose.secrets.yaml` | Optional overlay: Django secret key from a file |
| `.env.example` | Every variable the files use. Copy to `.env` (never commit `.env`) |
| `backend/Dockerfile` | Chapter 51's Dockerfile plus the `/app/media` ownership lines |
| `tools/composelint.py` | Compose policy checker (needs PyYAML: `pip install pyyaml`) |
| `tools/test_compose_files.py` | 40 tests (no Docker needed) |

Checks (together with Chapter 51's tools these are 83 tests):

    python3 tools/composelint.py .
    python3 -m unittest discover -s tools

Docker Compose itself was not available where this was written, so `docker compose`
was never run against these files. Section 52.12 is the first real run.
