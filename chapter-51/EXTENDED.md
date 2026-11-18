# Chapter 51 — Docker Fundamentals: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Why Containers › What we will containerize

The AI Chat app has five moving parts. Two of them we build ourselves; the other two come ready-made from the maintainers of PostgreSQL and Redis. Notice that Django, the Channels worker, Celery and Celery Beat share one image and differ only in the command they run. One image to build, scan and deploy is easier than four.

| **Piece** | **Image** | **Where it comes from** | **Used in** |
|---|---|---|---|
| **Django API over ASGI (Chapter 11 to 14)** | `ai-chat-backend` | We build it: section 51.7 | Chapters 52, 54 |
| **Channels worker, Celery worker, Celery Beat (Chapters 14, 15)** | the same `ai-chat-backend` | Same image, different command | Chapter 52 |
| **Next.js web app (Chapter 18)** | `ai-chat-frontend` | We build it: section 51.8 | Chapters 52, 54 |
| **PostgreSQL** | `postgres:18` | Official image | Chapter 52 |
| **Redis (cache, channel layer, Celery broker)** | `redis:8` | Official image | Chapter 52 |


## Running Containers: The Everyday Commands › Your first real container

Start a Redis server in the background, talk to it, read its log and remove it:

**bash terminal**

```bash
docker run -d --name chat-redis --rm redis:8
docker ps
docker exec -it chat-redis redis-cli ping
docker logs chat-redis
docker stop chat-redis
```

**text typical output**

```text
$ docker exec -it chat-redis redis-cli ping
PONG
$ docker ps
CONTAINER ID   IMAGE     COMMAND                  STATUS         NAMES
3f2a9c1d7b4e   redis:8   "docker-entrypoint.s..."   Up 5 seconds   chat-redis
```

**Check:** "PONG" comes back. After `docker stop`, `docker ps -a` no longer lists `chat-redis`, because `--rm` deleted the container as soon as it stopped.

Here is what each flag did. You will meet them in every Docker guide, so they are worth remembering.

| **Flag** | **Meaning** | **Use it when** |
|---|---|---|
| `-d` | Detached: run in the background | Servers. Leave it off to watch output in your terminal |
| `--name` | Give the container a name instead of a random one | Always, so you can refer to it |
| `--rm` | Delete the container when it stops | Throwaway and one-off commands |
| `-p HOST:CONTAINER` | Publish a container port on the host | Only for things that must be reachable from outside |
| `-e NAME=value`, `--env-file` | Set environment variables | Configuration (never put real secrets here; see below) |
| `-v SOURCE:TARGET` | Mount a volume or folder | Data that must survive, or config files |
| `--network` | Attach to a named network | Containers that must find each other by name |
| `--restart unless-stopped` | Start again after a crash or reboot | Servers (Compose handles this in Chapter 52) |


## Running Containers: The Everyday Commands › Publishing ports without opening the door to the world

A container has its own network, so nothing outside can reach it until you **publish** a port. `-p 6379:6379` publishes on every network interface of the host, which usually means the whole internet if the machine has a public address. Add the address in front to restrict it to your own machine:

**bash terminal**

```bash
# Reachable only from this computer (localhost):
docker run -d --name chat-redis --rm -p 127.0.0.1:6379:6379 redis:8
 
# Reachable from every network the host is on (almost never what you want):
docker run -d --name chat-redis --rm -p 6379:6379 redis:8
```

> **Docker can punch through your firewall**
>
> On Linux, Docker writes its own firewall rules for published ports, and they are applied before the rules that tools such as UFW manage. A port published with `-p 5432:5432` can be reachable from the internet even though `ufw status` looks like it denies it. Chapter 53 sets up the server firewall and returns to this. The habit that protects you is simple and starts today: **bind published ports to** `127.0.0.1`**, or do not publish them at all.** Databases and Redis should never be published on a server (Chapter 17: private data stores).


## Volumes: Keeping Data After the Container Is Gone › PostgreSQL with a volume and a secret file

First create a private network (section 51.5 explains why), a volume and a password file. The `secrets/` folder must never be committed, so add it to `.gitignore` as well:

**bash terminal**

```bash
cd ~/projects/ai-chat-app
mkdir -p secrets
python3 -c "import secrets; print(secrets.token_urlsafe(24))" > secrets/db_password
chmod 600 secrets/db_password
echo "secrets/" >> .gitignore
 
docker network create appnet
docker volume create chat-pgdata
```

**bash terminal**

```bash
docker run -d --name db --network appnet \
  -e POSTGRES_USER=chat -e POSTGRES_DB=chat \
  -e POSTGRES_PASSWORD_FILE=/run/secrets/db_password \
  -v "$PWD/secrets/db_password:/run/secrets/db_password:ro" \
  -v chat-pgdata:/var/lib/postgresql \
  postgres:18
```

> **PostgreSQL 18 moved its data directory**
>
> Images before version 18 kept data in `/var/lib/postgresql/data`, and every older tutorial mounts a volume there. From version 18 the image keeps data in a version-numbered folder below `/var/lib/postgresql`, and its documentation recommends mounting the volume at `/var/lib/postgresql`. Follow the old tutorials with a version 18 image and your database may live somewhere other than the volume you think it does, which you discover the day you delete the container. If you pin an older major version, use the path that version's documentation shows.

Now prove to yourself that the data survives. Create a table, delete the container completely, start a new one with the same volume and look again:

**bash terminal**

```bash
docker exec db psql -U chat -d chat \
  -c "create table note(id int); insert into note values (1);"
docker rm -f db
# run the same "docker run ... postgres:18" command from above again, then:
docker exec db psql -U chat -d chat -c "select * from note;"
```

**text typical output**

```text
 id
----
  1
(1 row)
```

**Check:** the row is still there, although the container that created it no longer exists. The volume held the data. (If `psql` reports that the server is not ready, wait a few seconds: PostgreSQL needs a moment to start.)

*(figure: see the printed book)*

*Containers on a private network; only two ports are published, and the database data lives in a volume.*

> **Three commands that delete data**
>
> - `docker volume rm NAME` deletes the volume and everything in it.
> - `docker system prune --volumes` deletes every volume no container is using right now, including a database volume whose container happens to be stopped.
> - `docker compose down -v` (Chapter 52) removes the project's volumes along with its containers.
> A volume is **not a backup**. It protects against deleting a container, not against deleting the volume, a full disk or a dead server. Chapter 55 covers real backups. Until then, `docker exec db pg_dump -U chat chat > backup.sql` takes a copy you can store somewhere else.


## The Django Image › The entrypoint script

The entrypoint runs optional start-up chores and then hands control to the real command. Two details deserve attention. `exec "$@"`  **replaces** the shell with your server, so the server becomes the main process and receives the stop signal from `docker stop`. And running migrations is controlled by `RUN_MIGRATIONS`, off by default: if you run four copies of the backend, you want exactly one of them to migrate, not four racing each other (Chapter 52 designates which).

**backend/docker/entrypoint.sh**

```
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
```

While writing the tests for this script, the test for "what happens when no command is given" failed. A plain `exec` with nothing to run does nothing and exits with success, so a container started without a command would look healthy-and-finished instead of broken. The `exit 64` guard at the top fixes that. This is why Chapter 51 is worth the effort: Dockerfile scripts are code, and code deserves tests.


## The Django Image › The health check

A health check answers one question: is the app actually answering requests, not just running as a process? Slim images have no `curl`, so ours uses Python's standard library. It has three details that each prevent a real problem:

- **It sends a** `Host` **header** (default `localhost`). Django answers any host not in `ALLOWED_HOSTS` with 400 Bad Request. Add `localhost` to `DJANGO_ALLOWED_HOSTS` (or set `HEALTHCHECK_HOST` to one of your real domains), or the container will report "unhealthy" while the app works.
- **It sends** `X-Forwarded-Proto: https`**.** If your production settings redirect HTTP to HTTPS, a plain-HTTP probe would get a 301 and fail. This header tells Django the request already arrived securely, provided your settings trust that header from the proxy, as the production block from Chapter 11 does.
- **It does not follow redirects.** A redirect is reported as `HTTP 301`, so the failure explains itself in `docker inspect`.
**backend/docker/healthcheck.py**

```
"""Container health check: exit 0 if the app answers 200, else exit 1.
 
The slim image has no curl, so we use Python. Settings (all optional):
  PORT              port the app listens on          (default 8000)
  HEALTHCHECK_PATH  URL path to request              (default /healthz/)
  HEALTHCHECK_HOST  Host header to send              (default localhost)
 
Django rejects unknown Host headers, so HEALTHCHECK_HOST (default "localhost") must be
in DJANGO_ALLOWED_HOSTS. We also send X-Forwarded-Proto: https so an HTTPS-redirect
setting does not answer our plain-HTTP probe with a 301. Redirects are NOT followed:
a 301 means "not healthy", and the message says so.
"""
import os
import sys
import urllib.error
import urllib.request
 
 
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None
 
 
def check(url: str, host: str = "localhost", timeout: float = 3.0) -> tuple[bool, str]:
    request = urllib.request.Request(
        url, headers={"Host": host, "X-Forwarded-Proto": "https"}
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status == 200:
                return True, "healthy"
            return False, f"unexpected status {response.status}"
    except urllib.error.HTTPError as exc:  # 3xx (not followed), 4xx and 5xx land here
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"cannot connect: {exc}"
 
 
def main() -> int:
    port = os.environ.get("PORT", "8000")
    path = os.environ.get("HEALTHCHECK_PATH", "/healthz/")
    host = os.environ.get("HEALTHCHECK_HOST", "localhost")
    ok, message = check(f"http://127.0.0.1:{port}{path}", host=host)
    print(message)
    return 0 if ok else 1
 
 
if __name__ == "__main__":
    sys.exit(main())
```

The endpoint it calls must exist. If Chapter 11 or 17 gave you a health URL, set `HEALTHCHECK_PATH` to it. Otherwise add this one. It checks that the process can answer, and deliberately does **not** touch the database: a **liveness** check that fails whenever PostgreSQL is briefly slow would make Docker restart a perfectly healthy backend. A deeper **readiness** check, which does query the database, belongs behind a separate URL (Chapter 55). As Chapter 17 requires, the public health endpoint declares itself public:

**core/views.py (add)**

```
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
 
 
@api_view(["GET"])
@permission_classes([AllowAny])  # public on purpose: Docker and the proxy call it
@throttle_classes([])            # a health check must never be rate limited
def healthz(request):
    """Liveness: the process is up and can answer. No database call, on purpose."""
    return JsonResponse({"status": "ok"})
```

**config/urls.py (add to urlpatterns)**

```
from core.views import healthz
 
urlpatterns += [path("healthz/", healthz)]
```


## The Next.js Image › What to notice

- **Three stages.**  `deps` installs with `npm ci` (exact versions from `package-lock.json`, and it fails if the lock file and `package.json` disagree). `builder` compiles the app. `runner` holds only the output. The same cache rule applies: `package.json` and the lock file are copied before the source.
- **Node version.**  `NODE_VERSION` is an `ARG`, so one line changes it. Node 24 is a supported long-term-support line; Node 26 was scheduled to become LTS on 28 October 2026. Check the Node release schedule and the Node versions your Next.js release supports before you pick, then use an even-numbered LTS line, never an odd-numbered one.
- **The** `node` **user.** The official Node image already contains a non-root user called `node`, so `USER node` is all that is needed.
- `HOSTNAME=0.0.0.0`**.** Docker sets a `HOSTNAME` variable to the container's id, and the standalone server would bind to that name only, which a published port cannot reach. Setting it explicitly is a well-known requirement for Next.js in Docker.
- **Three** `COPY` **lines for output.** The standalone folder does not include `public/` or `.next/static/`, so we copy them in. If your project has no `public/` folder, create an empty one or remove that line. If you use a monorepo, the location of `server.js` inside `standalone/` changes with the folder structure.
> **NEXT_PUBLIC_ values are frozen into the image at build time**
>
> Next.js replaces every `NEXT_PUBLIC_...` variable with its literal value **while building**, and ships that value in the JavaScript sent to every visitor. Two consequences follow:
>
> - **Setting** `NEXT_PUBLIC_API_URL` **when the container starts does nothing.** The value was already baked in. Pass it with `--build-arg` at build time, and build a separate image for each environment (staging and production). Dokploy builds on your server (Chapter 54), so there you set it as a build argument.
> - **Never put a secret in a** `NEXT_PUBLIC_` **variable, or in any** `ARG` **used for building.** Anyone can read the compiled JavaScript, and `docker history` shows build arguments. Chapter 17's rule holds: the browser only ever receives public values.
> Server-only values that code reads at run time, such as the internal address `http://backend:8000` for server components, are different. They are ordinary environment variables, set when the container starts. Pages that Next.js renders statically at build time still capture the value they saw during the build, so keep run-time configuration in dynamic routes.

The health check uses Node's built-in `fetch` to request the home page. If your home page redirects unauthenticated visitors, `fetch` follows the redirect, which is fine as long as the final page answers with success. A dedicated `app/api/health/route.ts` that returns a small JSON body is cleaner, and Chapter 52 can point to it.

> **Using pnpm or Yarn**
>
> If Chapter 18's project uses pnpm, replace the `deps` stage with `RUN corepack enable` followed by `pnpm install --frozen-lockfile` after copying `pnpm-lock.yaml`, and change the cache mount target to pnpm's store. Everything else stays the same. The policy checker in Chapter 51 recognises `pnpm install` and `yarn install` too.


## Smaller, Faster and Safer Images › Habits that make images safe

These are Chapter 17's rules, applied to images:

| **Habit** | **How** | **What it prevents** |
|---|---|---|
| **Run as non-root** | `USER app` / `USER node` | An exploited app having root inside the container |
| **No secrets in the image** | `.dockerignore`, no `ENV`/`ARG` secrets; mount `_FILE` secrets at run time | A pulled image, a leaked registry token or `docker history` exposing keys |
| **Pin base images** | `python:3.13-slim`, optionally `@sha256:...` | A surprise change under a tag you thought was stable |
| **Rebuild regularly** | Rebuild and redeploy at least monthly | Known vulnerabilities in the base image's packages |
| **Scan the image** | `docker scout cves IMAGE`, or Trivy: `trivy image IMAGE` | Shipping packages with published vulnerabilities |
| **Least privilege at run time** | `--read-only --tmpfs /tmp --cap-drop=ALL --security-opt no-new-privileges` | An attacker writing files, or gaining extra privileges |

The run-time flags in the last row make the container's filesystem read-only, give it a scratch folder in memory, remove every special Linux capability and stop processes from gaining new privileges. Try them on the backend once it runs: if something needs to write (a media folder, say), give that path a volume or a `--tmpfs` rather than making the whole filesystem writable.


## Smaller, Faster and Safer Images › A secret you need only while building

Sometimes the build itself needs a credential, such as a token for a private package index. An `ARG` or `ENV` would store it in the image history. A **build secret** is mounted for one `RUN` command and never written to a layer:

**Dockerfile (fragment)**

```dockerfile
RUN --mount=type=secret,id=pip_token \
    TOKEN="$(cat /run/secrets/pip_token)" \
    && pip install --index-url "https://__token__:${TOKEN}@pypi.example.com/simple" \
         -r requirements.lock.txt
```

**bash terminal**

```bash
docker build --secret id=pip_token,src=./secrets/pip_token -t ai-chat-backend:dev .
```

The private index address in the fragment is a placeholder for your own. Never pass the token with `--build-arg`.


## Debugging Containers

A container that will not start is the most common Docker problem, and it has a short, reliable routine. Start with what the container says, then how it ended, then look inside.

**bash terminal**

```bash
docker ps -a                       # was it created, is it running, did it exit?
docker logs backend                # what the app printed before it stopped
docker inspect --format '{{.State.ExitCode}}' backend
docker inspect --format '{{json .State.Health}}' backend   # health history
 
# Override the entrypoint to get a shell in a fresh container of the same image:
docker run --rm -it --entrypoint sh ai-chat-backend:dev
```

The **exit code** is a strong clue. Codes above 128 mean the process was ended by a signal: the number minus 128 is the signal.

| **Exit code** | **Meaning** | **What to do** |
|---|---|---|
| **0** | The process finished normally | A server should not do this. Check that `CMD` runs a long-lived process |
| **1** | The app raised an error | Read `docker logs`: a traceback, a missing setting or a missing secret |
| **64** | Our entrypoint was given no command | Set `CMD`, or pass a command after the image name |
| **126 or 127** | Command not executable, or not found | Wrong path in `CMD`, a missing file, or Windows line endings in a script |
| **137** | Killed (signal 9) | Often out of memory: check `docker stats` and raise the limit; or `docker stop` timed out |
| **139** | Crashed (segmentation fault) | Usually a broken native library or wrong architecture |
| **143** | Stopped by SIGTERM | Normal for `docker stop`; not an error |

Two last tools. `docker cp NAME:/app/file.txt .` copies a file out of a container for a closer look. And remember that anything you change inside a running container is lost when it is replaced: fix the Dockerfile or the configuration, rebuild and run again.


## Checking Your Dockerfiles Automatically

Everything in sections 51.6 to 51.9 is a habit, and habits slip: someone adds `ENV API_TOKEN=...` in a hurry, or deletes a line from `.dockerignore` to "fix" a build. A pull request review might notice, and might not. So this chapter ships a small checker, `tools/dockerlint.py`, that turns the habits into rules a machine enforces on every pull request. It uses only the Python standard library and does not need Docker.

| **Rule** | **Checks that...** | **Section** |
|---|---|---|
| **DL001** | Every base image has a version tag (not missing, not `latest`); a digest or a build `ARG` is accepted | 51.2 |
| **DL002** | The final stage ends as a non-root `USER` | 51.7 |
| **DL003** | The Dockerfile has more than one stage | 51.7 |
| **DL004** | `apt-get` uses `--no-install-recommends`, updates and installs in one `RUN`, and cleans `/var/lib/apt/lists` | 51.9 |
| **DL005** | `COPY . .` does not come before the dependency install in the same stage | 51.6 |
| **DL006** | No `ENV` or `ARG` named like a secret (`SECRET`, `PASSWORD`, `TOKEN`, `API_KEY`, ...); `NEXT_PUBLIC_*` and `*_FILE` names are allowed | 51.8 |
| **DL007** | The final stage defines a `HEALTHCHECK` | 51.7 |
| **DL008** | `CMD` and `ENTRYPOINT` use the JSON (exec) form | 51.6 |
| **DL009** | No `.env` file is copied in, and `ADD` is used only for URLs and archives | 51.6 |
| **DL010** | `pip install` uses `--no-cache-dir` or a cache mount | 51.9 |
| **DI001** | `.dockerignore` excludes `.env`, `.git` and the language's junk (`.venv`, `node_modules`, `.next`, ...) | 51.6 |
| **DI002** | `.dockerignore` re-includes nothing except `!.env.example` | 51.6 |

Run it on the naive Dockerfile from section 51.6, with a secret added to make it more realistic. Every finding names the rule, the line and what to do:

**text verified output**

```text
FAIL /tmp/Dockerfile.bad
  DL001 line 1: Base image 'python' has no tag, so it means 'latest'. Pin a version.
  DL003 line 1: Single-stage build: build tools end up in the final image.
    Use a multi-stage build.
  DL002 line 1: The final stage never sets USER, so the app runs as root.
  DL007 line 1: The final stage has no HEALTHCHECK.
  DL008 line 5: CMD uses shell form. Use the JSON (exec) form so signals reach your process.
  DL006 line 2: ENV DJANGO_SECRET_KEY looks like a secret. Values in ENV and ARG
    are visible in 'docker history' and 'docker inspect'. Pass secrets at run
    time, or use a build secret.
  DL010 line 4: pip install keeps a download cache in the layer.
    Use --no-cache-dir or a cache mount.
  DL005 line 3: COPY . . comes before the dependency install, so every code
    change reinstalls dependencies. Copy only the dependency files first.
```

(Long messages are wrapped here for the page; the tool prints each finding on one line.) Run against this chapter's real files it prints one `OK` line per file and exits with code 0:

**text verified output**

```text
OK   backend/Dockerfile
OK   backend/.dockerignore
OK   frontend/Dockerfile
OK   frontend/.dockerignore
```

The test suite in `tools/test_docker_files.py` has 43 tests. Besides the rules above (each has a failing example and a passing one), it tests the scripts from section 51.7: the wait script against real local sockets (up, never up, and a service that starts late), the health check against a throwaway web server answering 200, 301, 400 and 500, and the entrypoint script run through a real shell with a stand-in `python`, to prove that arguments survive intact, exit codes pass through and migrations run only when asked. None of it needs Docker.

**text verified output**

```text
$ python -m unittest discover -s tools
...........................................
----------------------------------------------------------------------
Ran 43 tests in 1.6s
 
OK
```

To make the checks part of every pull request, add a small GitHub Actions workflow (Chapter 50 covered CI). Use the current major versions of the two actions:

**.github/workflows/docker-policy.yml**

```
name: docker-policy
on: [pull_request]
 
jobs:
  policy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: python -m unittest discover -s tools -v
      - run: >
          python tools/dockerlint.py
          backend/Dockerfile backend/.dockerignore
          frontend/Dockerfile frontend/.dockerignore
```

> **This checker is a safety net, not a full linter**
>
> It understands the rules above and nothing else, and it does not parse heredoc syntax. For wider coverage, add **hadolint**, a dedicated Dockerfile linter, and run `docker build --check .`, which makes BuildKit report common Dockerfile mistakes. They complement each other: hadolint knows hundreds of rules, and ours knows the ones this book's app depends on.
