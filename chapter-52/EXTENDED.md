# Chapter 52 — Docker Compose for Full-Stack Apps: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## From Many Commands to One File › The things worth knowing before you write a line

- **The command is** `docker compose` **(with a space).** It is a plugin of the Docker CLI, usually called Compose v2. The older hyphenated `docker-compose` is the retired first version; if a tutorial uses it, translate it.
- **Name the file** `compose.yaml`**.** Compose also finds `docker-compose.yml`, but `compose.yaml` is the current standard name.
- **Do not write a** `version:` **line.** Old files start with `version: "3.8"`. Modern Compose ignores it and prints a warning, so we leave it out (our checker flags it).
- **A project name groups everything.** We set `name: ai-chat`. Containers become `ai-chat-db-1`, volumes `ai-chat_pgdata`, and the private network `ai-chat_default`. Two projects with different names can run side by side on one machine without colliding.
- **Every service joins the project's network and is reachable by its service name.** The backend connects to `db:5432` and `redis:6379`, exactly as in Chapter 51, with no network to create by hand.
- **Compose is the right size for one server.** Docker Swarm and Kubernetes spread containers over many machines. The AI Chat app on one VPS does not need either, and Chapter 54's Dokploy runs Compose projects directly.
Here is the stack we are about to define. Notice that five of the services use the **same** backend image from Chapter 51 and differ only in their command, and that only the frontend and backend are reachable from outside.

*(figure: see the printed book)*

*Seven services (plus a one-shot migration job) in one project; only the frontend and backend are reachable from outside.*

| **Service** | **Runs** | **Lives how long** | **Reachable from outside?** |
|---|---|---|---|
| `db` | PostgreSQL 18 | Always | No |
| `redis` | Redis 8: cache, channel layer, Celery broker | Always | No |
| `migrate` | `manage.py migrate`, then exits | Seconds, once per deployment | No |
| `backend` | Django over ASGI (Uvicorn), API and WebSockets | Always | Yes, through a proxy |
| `channels-worker` | `manage.py runworker`, only if your design needs it | Always (optional profile) | No |
| `celery-worker` | Background jobs (Chapter 15) | Always | No |
| `celery-beat` | The scheduler for periodic tasks | Always, exactly one | No |
| `frontend` | Next.js standalone server | Always | Yes, through a proxy |


## The Base File, Part 2: The Django Family › channels-worker (optional)

Chapter 14's WebSockets are served by the ASGI backend itself, so most designs need no separate worker. A dedicated process is only for background Channels consumers that you start with `manage.py runworker`. The service therefore carries `profiles: ["channels"]`, which means `docker compose up` ignores it unless you ask: `docker compose --profile channels up -d`. Replace the placeholder channel name with the ones your project defines, through `CHANNEL_NAMES` in `.env`.


## The Base File, Part 3: Next.js and the Volumes

**compose.yaml (frontend and volumes)**

```
  # ------------------------------------------------------------ Next.js
  frontend:
    image: ${FRONTEND_IMAGE:-ai-chat-frontend}:${APP_VERSION:-dev}
    build:
      context: ./frontend
      args:
        NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:?Set NEXT_PUBLIC_API_URL in .env}
        NEXT_PUBLIC_WS_URL: ${NEXT_PUBLIC_WS_URL:?Set NEXT_PUBLIC_WS_URL in .env}
    environment:
      BACKEND_INTERNAL_URL: http://backend:8000
    depends_on:
      backend:
        condition: service_healthy
 
volumes:
  pgdata:
  redisdata:
  media:
```

- `build.args` **pass the public URLs at build time**, as Chapter 51 taught: `NEXT_PUBLIC_` values are frozen into the JavaScript. The `:?` forms mean you cannot build the frontend without choosing them. Change either value in `.env`, run `docker compose build frontend`, and recreate the service.
- `BACKEND_INTERNAL_URL` **is an ordinary run-time variable.** Next.js server code calls the backend by service name; the browser uses the public URL. Chapter 51's "which address do I use?" table in action.
- **It waits for the backend to be healthy**, so the first visitor never meets a frontend whose API is still starting.
- **No health check is written here**, because the Dockerfile from Chapter 51 already defines one that the service inherits.
- **Three named volumes**, declared at the bottom with no options. Compose creates them on first use and keeps them until you delete them.
> **One line to add to Chapter 51's Dockerfile**
>
> The `media` volume mounts at `/app/media`. When a named volume is mounted over a folder that exists in the image, Docker copies the folder's ownership into the new volume. If the folder does not exist, the volume is created owned by **root**, and the non-root `app` user cannot write uploads to it. The fix is one line in `backend/Dockerfile`, just after `WORKDIR /app`: replace `RUN chown app:app /app` with `RUN chown app:app /app && mkdir -p /app/media && chown app:app /app/media`. The updated Dockerfile is in this chapter's code zip. The same trap applies to any writable folder you mount a volume on.


## Health Checks and Start-up Order › Three conditions

| **Condition** | **Compose waits until...** | **Used for** |
|---|---|---|
| `service_started` | The container has been started (it may not be ready) | Rarely enough; avoid for data stores |
| `service_healthy` | The dependency's health check reports **healthy** | `db`, `redis`, `backend` |
| `service_completed_successfully` | The dependency **exited with code 0** | The `migrate` job |

A condition `service_healthy` only works if the dependency **has** a health check. Without one, Compose cannot ever call it healthy, and the dependent service never starts. The checker in Chapter 52 catches this.


## Environment Variables: Three Places, Three Jobs › See what Compose understood

Before the first start, and whenever something behaves oddly, ask Compose to print the final, merged, variable-expanded configuration:

**bash terminal**

```bash
docker compose config           # the full resolved configuration
docker compose config -q        # only validate: silent when fine, exit code 1 when not
docker compose config --services
```

> **docker compose config prints your secrets**
>
> The resolved output contains the real values of every variable, including passwords. Never paste it into a chat, a ticket or an AI assistant, and never let a CI job print it into a build log (Chapter 17's logging rules apply). Use `docker compose config -q` when you only need to know whether the file is valid.


## Secrets: Keeping Values Out of the Environment › The permission trap

File secrets in plain Compose are **bind mounts**: the file on the host is shown inside the container unchanged. Compose accepts `uid`, `gid` and `mode` options for a secret, but for a file source they are **ignored**, because a bind mount cannot change ownership. The container user (`app`, id 10001, from Chapter 51) is not you, so a file owned by you with mode `600` fails with `Permission denied`.

The practical fix uses a detail of how bind mounts work: Docker opens the file itself, so the container does **not** need access to the folder that holds it. Lock the folder and relax only the file:

**bash terminal**

```bash
mkdir -p secrets
chmod 700 secrets                      # only you can enter the folder
python3 -c "import secrets; print(secrets.token_urlsafe(50))" > secrets/django_secret_key
chmod 644 secrets/django_secret_key    # the container user can read this one file
```

**Check:** `ls -ld secrets` shows `drwx------`. Other accounts on the host cannot list or open anything in the folder, while the container can read exactly the one file you mount.

Add `secrets/` to `.gitignore` (Chapter 51 already did) and then switch the overlay on by appending `:compose.secrets.yaml` to `COMPOSE_FILE` in `.env`. Verify it the same way you verified Chapter 51's image:

**bash terminal**

```bash
docker compose up -d
docker compose exec backend env | grep -i secret
```

**text typical output**

```text
DJANGO_SECRET_KEY=
DJANGO_SECRET_KEY_FILE=/run/secrets/django_secret_key
```

Two honest limits remain. `DATABASE_URL` contains the database password, so that password is still an environment variable; moving it to a file needs `DATABASE_URL_FILE` support in your settings (one line with Chapter 17's helper) and removing the variable from the base file, which is Exercise 5. And newer Compose versions can build a secret file from an environment variable and honour `uid`, `gid` and `mode` for it, which suits platforms such as Dokploy that hand you environment variables; check your Compose version's documentation before relying on it.


## Development and Production from One Project › compose.prod.yaml

**compose.prod.yaml**

```
# compose.prod.yaml: production-like settings. No published ports: a reverse proxy
# (Chapter 54) reaches the containers over the Docker network.
x-prod: &prod
  restart: unless-stopped
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"
  security_opt:
    - no-new-privileges:true
 
# For our own non-root containers: also drop every Linux capability.
x-prod-app: &prod-app
  <<: *prod
  cap_drop:
    - ALL
 
services:
  db:
    <<: *prod
 
  redis:
    <<: *prod
 
  migrate:
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
 
  backend:
    <<: *prod-app
    deploy:
      resources:
        limits:
          memory: 1g
 
  celery-worker:
    <<: *prod-app
    deploy:
      resources:
        limits:
          memory: 1g
 
  celery-beat:
    <<: *prod-app
 
  channels-worker:
    <<: *prod-app
 
  frontend:
    <<: *prod-app
    deploy:
      resources:
        limits:
          memory: 512m
```

- **Two anchors, one on top of the other.**  `x-prod` holds the restart policy, log rotation and `no-new-privileges`; `x-prod-app` adds `cap_drop: ALL` for our own non-root containers.
- **Log rotation matters.** Docker's default logging driver keeps every line forever, and a chatty app eventually fills the server's disk. Three files of 10 MB each cap it.
- `db` **and** `redis` **are not capability-stripped.** Their official images start as root to fix file ownership and then drop to their own user; removing capabilities would stop them from starting. Hardening them is a job for the image, not for us.
- `migrate` **gets no restart policy**, so it inherits `restart: "no"` from the base. It is a job.
- **Memory limits protect the neighbours.** A runaway worker is killed by the kernel (exit code 137, Chapter 51) instead of starving PostgreSQL. Tune the numbers once you watch real usage (Chapter 55).
- **There is no** `ports:`**.** Chapter 54's reverse proxy connects over the Docker network. If you ever test production settings locally and need a port, add one in a separate untracked file rather than editing this one.

## Checking the Compose Files Automatically

As in Chapter 51, the habits are only as good as their enforcement, and Compose files are even easier to break quietly: delete one `condition:` line and the stack still starts, just with a race in it. The chapter ships `tools/composelint.py`, which reads the files (it needs the PyYAML package) and applies these rules:

| **Rule** | **Checks that...** | **Section** |
|---|---|---|
| **CL001** | Every image is pinned (no missing tag, no `latest`); a `${VARIABLE}` tag is accepted | 52.3 |
| **CL002** | Published ports are bound to `127.0.0.1`; production publishes none | 52.9 |
| **CL003** | Production services have a restart policy; the `migrate` job has `restart: "no"` | 52.4 |
| **CL004** | `depends_on` names real services with a condition, and anything waited on as healthy has a health check | 52.6 |
| **CL005** | No literal secret in `environment` (names like `PASSWORD`, `SECRET`, `TOKEN`, `API_KEY`) | 52.8 |
| **CL006** | Every `${VARIABLE}` without a default appears in `.env.example` | 52.7 |
| **CL007** | PostgreSQL's volume uses the version 18 path | 52.3 |
| **CL008** | Production has log rotation, `no-new-privileges`, and `cap_drop: ALL` on app containers | 52.9 |
| **CL009** | Celery Beat is not scaled beyond one instance | 52.4 |
| **CL010** | `.env.example` sets `COMPOSE_FILE` | 52.9 |
| **CL011** | `DJANGO_DEBUG` is not `true` outside the dev overlay | 52.9 |
| **CL012** | No obsolete top-level `version:` | 52.1 |
| **CL013** | Health check commands escape `$` as `$$` | 52.3 |

Run it on a sloppy file with the usual beginner problems, and every finding names the rule, where it is and what to do:

**text verified output**

```text
FAIL compose files
  CL012 [compose.yaml]: Top-level 'version:' is obsolete; remove it.
  CL001 [compose.yaml:db]: Image 'postgres' has no tag. Pin a version.
  CL002 [compose.yaml:db]: Port '5432:5432' is not bound to 127.0.0.1.
  CL005 [compose.yaml:db]: POSTGRES_PASSWORD has a literal value. Use
    ${POSTGRES_PASSWORD} from .env, or a secret file.
  CL013 [compose.yaml:db]: Healthcheck uses $NAME unescaped. Compose expands it
    first; write $$NAME.
  CL007 [compose.yaml:db]: PostgreSQL 18+ keeps data below /var/lib/postgresql.
    Mount the volume there.
  CL004 [base:backend]: depends_on names unknown service 'cache'.
```

(Long messages are wrapped here for the page.) On this chapter's real files it prints a single `OK` line and exits with code 0. The 40 tests in `tools/test_compose_files.py` go further than the rules alone:

- **Every rule has a failing and a passing example**, and each was also proved by breaking the real files on purpose (opening the database port, weakening the migration wait, removing a restart policy, using the old Postgres path): the suite failed every time.
- **The start-up order is tested** as written in Chapter 52: who waits for whom, with which condition.
- **The merged development and production views are tested**: ports appended and bound to localhost, code mounted in dev, and in production restart, log rotation and hardening on every service with no ports published.
- **A small stand-in for variable expansion proves the files resolve.** With the values from `.env.example`, `DATABASE_URL` becomes `postgres://chat:...@db:5432/chat`, the image tag and the frontend build arguments resolve, `$$` survives for the container's shell, and a missing `POSTGRES_PASSWORD` stops with the `:?` message.
Remember the limit from the verification box: the merge in these tests is a simplified copy of Compose's rules, so `docker compose config` stays the final authority. That is why the CI job below runs both. Add these steps to the workflow from Chapter 51 (the runner already has Docker and Compose):

**.github/workflows/docker-policy.yml (add these steps)**

```
      - run: pip install pyyaml
      - run: python tools/composelint.py .
      - run: cp .env.example .env && docker compose config -q
      - run: docker compose -f compose.yaml -f compose.prod.yaml config -q
```
