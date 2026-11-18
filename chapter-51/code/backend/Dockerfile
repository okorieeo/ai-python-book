# syntax=docker/dockerfile:1
# Backend image for the AI Chat app (Django + Channels + Celery use this ONE image).
# Build from the backend/ folder:  docker build -t ai-chat-backend:dev .

# ---------- Stage 1: builder (compilers live here and are thrown away) ----------
FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Tools needed only to BUILD Python packages (psycopg, cryptography, ...)
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# A virtual environment we can copy into the final image as one folder
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
# Copy ONLY the dependency list first, so this slow layer stays cached
# until the dependencies change (not every time your code changes).
COPY requirements.lock.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.lock.txt

# ---------- Stage 2: runtime (what we actually ship) ----------
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

# Only the shared library psycopg needs at run time (no compilers)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 \
 && rm -rf /var/lib/apt/lists/*

# A real user with no login shell and no password: the app never runs as root
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app \
        --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
RUN chown app:app /app
COPY --chown=app:app . .

USER app

# collectstatic imports your settings, which (Chapter 17) refuse to start without a
# secret. The placeholder exists ONLY for this one command: it is not an ENV, so
# running containers never inherit it. (The command text does appear in the build
# history, which is fine for a meaningless placeholder and never OK for a real
# secret.) Delete this line if you do not use collectstatic.
RUN DJANGO_SECRET_KEY=build-time-placeholder python manage.py collectstatic --noinput

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "/app/docker/healthcheck.py"]

ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
