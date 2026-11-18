# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS deps
COPY requirements.lock.txt .
RUN pip install --prefix=/install -r requirements.lock.txt

FROM base AS runtime
RUN useradd --create-home --uid 10001 app
COPY --from=deps /install /usr/local
COPY --chown=app:app . .
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
# daphne serves HTTP and WebSockets (Channels) from one process
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
