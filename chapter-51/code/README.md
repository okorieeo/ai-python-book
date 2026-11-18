# Chapter 51 code: Docker Fundamentals

Copy these files into the AI Chat project (see section 51.13 of the chapter):

| File | Purpose |
|---|---|
| `backend/Dockerfile`, `backend/.dockerignore` | Multi-stage Django (ASGI) image, non-root, health check |
| `backend/docker/entrypoint.sh` | Optional wait-for-services and migrations, then `exec "$@"` |
| `backend/docker/healthcheck.py` | Container health check (standard library only) |
| `backend/docker/wait_for.py` | Wait until `host:port` accepts connections |
| `frontend/Dockerfile`, `frontend/.dockerignore` | Three-stage Next.js standalone image, non-root |
| `frontend/next.config.ts` | Shows the `output: "standalone"` line. MERGE it into your own file |
| `tools/dockerlint.py` | Policy checker for Dockerfiles and .dockerignore files |
| `tools/test_docker_files.py` | 43 tests (no Docker needed) |
| `.gitattributes` | Keeps Unix line endings for scripts |

Run the checks (Python 3.12+, no packages to install):

    python3 tools/dockerlint.py backend/Dockerfile backend/.dockerignore frontend/Dockerfile frontend/.dockerignore
    python3 -m unittest discover -s tools

Note: the Dockerfiles themselves were not built where this was written (no Docker
engine available). Section 51.13 of the chapter is the first real build.
