#!/bin/sh
# Container entrypoint: optional start-up chores, then hand over to the real command.
#
#   WAIT_FOR="db:5432 redis:6379"   wait until these host:port pairs accept connections
#   WAIT_FOR_TIMEOUT=60             seconds to wait before giving up
#   RUN_MIGRATIONS=true             run "manage.py migrate" first (set on ONE service only)
set -eu

if [ "$#" -eq 0 ]; then
    # Plain "exec" with no command does nothing and exits 0: a container that
    # "succeeds" without running anything. Fail loudly instead.
    echo "entrypoint: no command given" >&2
    echo "(set CMD in the Dockerfile, or pass a command to docker run)" >&2
    exit 64
fi

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -n "${WAIT_FOR:-}" ]; then
    # WAIT_FOR is meant to split into several words, so it is left unquoted on purpose
    # shellcheck disable=SC2086
    python "$HERE/wait_for.py" --timeout "${WAIT_FOR_TIMEOUT:-60}" $WAIT_FOR
fi

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    python manage.py migrate --noinput
fi

# "exec" replaces this shell with the real process, so it becomes PID 1 and receives
# SIGTERM from "docker stop" directly. Without it, shutdowns are slow and unclean.
exec "$@"
