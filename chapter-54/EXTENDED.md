# Chapter 54 — Deploying with Dokploy: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## What Dokploy Is and How It Works › Our deployment design

Chapter 52’s Compose file had seven services in one file. For production we split it, and the reason is worth understanding because it shapes the whole chapter:

- **Stateless app services stay in a Compose project.** The Next.js server, the Django ASGI server, the Channels worker, the Celery worker and Celery Beat contain no data. They can be thrown away and rebuilt at any time, so they belong in a file that is redeployed on every push.
- **PostgreSQL and Redis become Dokploy Databases.** They hold data, so they should **not** be recreated with every deploy. As Dokploy Databases they are never touched by an app deploy, they get a proper connection page with credentials, and PostgreSQL gets scheduled **logical backups** (pg_dump files) to S3 with a restore button.
This is a design choice, not a law. Keeping the databases in the Compose file works too, but then your only backup option is a file-level copy of the data volume, which is harder to restore and riskier to take while the database is running.


## What Dokploy Is and How It Works › Two ways to get code onto the server

| **Approach** | **How it works** | **Good for** | **Cost** |
|---|---|---|---|
| **Build on the server** | Dokploy clones your repo and runs docker compose up --build on the VPS | Learning and small projects: nothing extra to set up | Builds use the server’s CPU and memory (the Next.js build is the one that hurts), and a failed build happens on the live machine |
| **Build in CI, pull on the server** | GitHub Actions builds and tests the images, pushes them to a registry, and Dokploy pulls the finished image | Production: the server only runs things, builds are reproducible, and Dokploy’s rollback and zero-downtime features work | More setup: a registry, image tags, a CI workflow |

We start with the first, because it works with the Compose file you already have and teaches the pieces. Section 54.7 shows how to move the pieces that matter to the second.


## Before You Install

The installer assumes a clean server and an open network. Check each item now, because most failed installs trace back to one of them.

> **Pre-install checklist**
>
> - **Chapter 53 is done:** you log in as deploy with a key, UFW is on, and the audit script passes except for the port 3000 warning.
> - **A snapshot exists** of the clean server (Chapter 53, step 12). Installing Dokploy changes Docker, networking and firewall rules, and a snapshot is the cheapest undo.
> - **Ports 80, 443 and 3000 are free.** Check with sudo ss -tulpn: nothing but SSH and the local resolver should be listening. Never install nginx or Apache here.
> - **Enough resources.** Dokploy’s documented minimum is 2 GB of RAM and 30 GB of disk; for our stack, use the sizes from 53.2.
> - **A supported system.** Dokploy’s installation page lists the Linux distributions it is tested on. At the time of writing its list reaches **Ubuntu 24.04 LTS**, so if you chose 26.04 LTS in Chapter 53, look at the page again today, and if 26.04 is not listed yet, use a 24.04 server for production.
> - **DNS is ready:** A records for deploy, app and api point at the server (53.9), and dig returns the right address.
> - **Docker is not installed yet,** or is the official Docker Engine. The installer installs Docker if it is missing.


## Installing Dokploy › When the installer fails

| **Message or symptom** | **Cause** | **Fix** |
|---|---|---|
| Error: port 80, 443 or 3000 is already in use | Something else is listening | Find it with sudo ss -tulpn and stop and remove it. A web server installed earlier is the usual culprit |
| could not choose an IP address to advertise | The server has more than one address (public, private or IPv6) and Swarm cannot pick | Tell it which: ADVERTISE_ADDR=203.0.113.10 sudo -E sh dokploy-install.sh, or set it inline as the Dokploy docs show |
| Swarm network overlaps with the provider’s private network | Docker’s default address ranges collide with a private network | Pass different Swarm address settings through DOCKER_SWARM_INIT_ARGS, as documented on Dokploy’s installation page |
| The script says it must run as root | sudo was left out | Use sudo sh dokploy-install.sh |
| Your distribution is not supported | An untested or very old system | Use a distribution on Dokploy’s tested list |
| The page at port 3000 does not load | Firewall or provider firewall | Check UFW and the cloud firewall allow 3000 (53.6) |

> **Create the administrator immediately**
>
> The very first visit to the panel creates the **administrator account**, and nobody checks who you are. Until you do it, a stranger who finds your server could claim it. So install Dokploy only when you are ready to complete the next section straight away.


## First Login, the Panel Domain and Closing Port 3000 › Harden Docker a little

Dokploy publishes a **production hardening guide**, and its main points match what you did in Chapter 53 (key-only SSH, a firewall, updates). Two items deserve action now.

**Limit container log size.** By default Docker keeps container logs forever, and a chatty application can fill the disk. Create /etc/docker/daemon.json (the file may not exist yet):

**bash terminal**

```bash
sudoedit /etc/docker/daemon.json
```

**json /etc/docker/daemon.json**

```json
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
```

**bash terminal**

```bash
sudo systemctl restart docker
sudo docker ps            # the services restart; check the panel still loads
```

This applies to **newly created containers**, so redeploy your services afterwards. Dokploy’s guide also lists other daemon options. Be selective: Docker documents that **live restore** does not work in Swarm mode, which Dokploy uses, so test any daemon change on a snapshot first rather than copying a whole configuration from a guide.

**Make the firewall apply to Docker.** Remember the Docker catch (53.6): ports published by containers bypass UFW. Dokploy’s guide recommends the **ufw-docker** tool (its GitHub project is chaifeng/ufw-docker) so that UFW rules also govern published container ports. It is optional, and it changes behaviour: after you install it, published ports are blocked unless you allow them, so you must explicitly allow ports 80 and 443 for Traefik and then test your sites. Try it on a snapshot first and read its README. The safer baseline, which you already follow, is simpler: **never publish a port you do not need**.


## Connecting GitHub

Dokploy needs read access to your repository to clone it on every deploy. It supports several sources (GitHub, GitLab, Bitbucket, Gitea, a plain Git URL and Docker images). For GitHub the best option is a **GitHub App**.

| **Option** | **How it authenticates** | **Trade-off** |
|---|---|---|
| **GitHub App** (recommended) | A private app you create from the panel, installed on your account or organisation | Per-repository access, no personal token, and it enables automatic deploys on push |
| **Deploy key** | An SSH key added to one repository, read-only | Simple and very narrow, but no automatic webhook setup |
| **Personal access token** | Your own token | Avoid: it carries your whole account’s power and expires |

In the panel, open the Git settings and choose to create a GitHub App. GitHub opens, asks you to confirm the app’s name and then which repositories to install it on. **Select only the repository you deploy**, not "all repositories", because anyone with the panel can use that access. Back in Dokploy, the repository now appears in the list when you create a service.

> **Your repository is part of the server's attack surface**
>
> Whoever can push to the deployed branch can run code on your server. Protect that branch: require pull requests, require the CI checks to pass, and require two-factor authentication on every GitHub account with write access. section 17.9 covers repository secrets and branch protection.


## Preparing the Project for Production › Two health endpoints

A health check is a URL that answers "are you OK?". We use two, and the difference matters:

| **Endpoint** | **Question** | **Touches the database?** | **If it fails** |
|---|---|---|---|
| /health/live | Is the process running? | **No** | The container is restarted |
| /health/ready | Can it do its job right now? | Yes: PostgreSQL and Redis | Traffic is held back |

If the liveness check also tested the database, a ten-second database hiccup would make every container look dead, and they would all restart at once and make the outage longer. The chapter code has the logic (backend_snippets/health_checks.py) and a thin Django wrapper. The readiness response names the failing check but never includes the error text, because exception messages can contain hostnames and credentials.

**python backend_snippets/health_checks.py (core idea)**

```python
def readiness(checks, timeout=2.0):
    failing = []
    ...  # run every check in parallel; a check that raises OR is slower than `timeout` is failing
    if failing:
        return 503, {"status": "unavailable", "failing": sorted(failing)}
    return 200, {"status": "ok"}
```

For Next.js add a route that returns {"status":"ok"} at /api/health, which the chat-web healthcheck calls.


## Preparing the Project for Production › Run the linter

The code includes a linter for the production Compose file. It reads the file and the committed .env example and checks the mistakes in the table above, plus several more. Run it now and in CI before every deploy:

**bash terminal (your laptop, in the repository)**

```bash
pip install pyyaml
python3 -m dokploycheck deploy/docker-compose.prod.yml --env-example deploy/.env.production.example
```

**text verified output: the chapter's compose file**

```text
[PASS] env example secrets: only placeholders
[PASS] compose network: dokploy-network is declared external
[PASS] compose: no problems found
```

And this is what it says about a Compose file written the way many tutorials do it (an excerpt from the real output; the full run reports 25 lines):

**text verified output: a risky compose file (excerpt)**

```text
[FAIL] env example SECRET_KEY: looks like a real secret in a file that is committed to Git: use CHANGE_ME or leave it empty
[FAIL] compose network: declare 'dokploy-network' with 'external: true' so Traefik and the Dokploy databases can reach your services
[FAIL] db ports: data store publishes ['5432:5432'] to the internet (Docker bypasses UFW): remove 'ports:'
[FAIL] db image: 'postgres:latest' is not pinned to a version: a redeploy can pull a different image
[FAIL] db POSTGRES_PASSWORD: secret written into the compose file: reference it as ${VAR:?message} instead
[FAIL] api docker.sock: mounting the Docker socket gives the container control of the server
[WARN] api volume: './media:/app/media' points into the repository, which Dokploy re-clones on each deploy: use a named volume or a Dokploy file mount
[FAIL] web NEXT_PUBLIC_STRIPE_SECRET_KEY: NEXT_PUBLIC_ values are baked into the JavaScript every visitor downloads: never put a secret there
[FAIL] variable NOT_IN_EXAMPLE: used in the compose file but not defined in the .env example (a deploy would run without it)
```


## Environment Variables and Secrets › Rules for secrets

- **Never commit real values.** The .env example holds placeholders only, and the linter fails if a secret-looking value appears in it.
- **Production keys are different keys.** A leaked test key is an annoyance; a leaked live key is an incident. Never reuse development keys.
- **Limit blast radius.** Give each external key the smallest permissions and a spending cap (an AI provider key without a limit can produce a surprising bill).
- **Keep a copy outside the panel.** Store the production values in your password manager. If the server dies, the panel’s copy dies with it.
- **Rotate when people leave or keys might have leaked,** and redeploy afterwards so containers receive the new values. Environment changes only take effect on the next deploy.

## Deploying the Compose Project › What happens during a deploy

| **Phase** | **What Dokploy does** | **Typical failure** |
|---|---|---|
| Clone | Fetches the branch into a working folder | Wrong branch name, no repository access |
| Build | docker compose build for services with a build: | Out of memory, a missing file, a network error while installing packages |
| Start | docker compose up -d, with dependencies first (migrate, then the app) | A missing variable, which the :? guard names in the log |
| Run | Containers start, healthchecks begin | The healthcheck path returns 404 or 500 |

Read the log from the **bottom** upwards to find the first real error. Then open the service’s **Logs** tab and choose a container (chat-migrate, chat-api) to see its output. A healthy API prints that it is listening on port 8000.

**bash terminal (on the server, if you want to look yourself)**

```bash
sudo docker ps --format 'table {{.Names}}\t{{.Status}}'
```

**text what you should see (names include a generated suffix)**

```text
NAMES                       STATUS
chat-app-chat-api-1         Up 1 minute (healthy)
chat-app-chat-web-1         Up 1 minute (healthy)
chat-app-chat-worker-1      Up 1 minute
chat-app-chat-beat-1        Up 1 minute
chat-app-chat-channels-1    Up 1 minute
```

The migrate container will not appear in docker ps because it has finished. If it failed, the API never starts: look at its log first.


## Domains and HTTPS › Check it, step by step

**bash terminal (your laptop)**

```bash
curl -sI https://app.example.com | head -3
curl -sI http://app.example.com | head -3          # should redirect to https
curl -s https://api.example.com/health/ready
```

**text what you should see**

```text
HTTP/2 200
HTTP/1.1 308 Permanent Redirect        (or 301)
Location: https://app.example.com/
{"status":"ok"}
```

**Test the HTTP redirect on purpose.** Dokploy’s hardening guide notes that for Compose domains the redirect from HTTP to HTTPS may need to be added by you, and the behaviour can differ between versions. If the second command returns 200 instead of a redirect, plain HTTP is being served. The fix is a router middleware label on the service, and since the exact label depends on your Dokploy version, follow its current Domains documentation and re-test until the redirect appears. The smoke test in Chapter 54 checks this on every deploy.


## Auto-Deploys › The CI-gated workflow

The chapter code includes .github/workflows/deploy.yml. It does three things in order: run the checks (here, the compose linter, plus the backend and frontend tests from Chapter 42 that you add), call Dokploy to deploy, then run the smoke test against the live site.

**yaml .github/workflows/deploy.yml (the important parts)**

```yaml
concurrency:
  group: deploy-production
  cancel-in-progress: false      # never cancel a deploy that has already started

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python -m dokploycheck deploy/docker-compose.prod.yml --env-example deploy/.env.production.example
  deploy:
    needs: test
    environment: production      # lets you require a manual approval in GitHub
    steps:
      - run: |
          curl --fail-with-body -sS -X POST "$DOKPLOY_URL/api/compose.deploy" \
            -H "x-api-key: $DOKPLOY_API_KEY" -H "Content-Type: application/json" \
            -d "{\"composeId\": \"$DOKPLOY_COMPOSE_ID\"}"
      - run: python -m dokploycheck.smoke --app https://app.example.com --api https://api.example.com --wait 600
```

A few details deserve attention:

- **API key.** In the panel, create an API key for the deploy (in the profile or settings area) and store it, the compose service’s ID and the panel URL as **GitHub Actions secrets**. The key can deploy to your server, so treat it like a password.
- **Confirm the endpoint.** The deploy endpoint name above follows Dokploy’s API pattern (the documented application deploy call has an equivalent for Compose). Look it up in the API reference for your version before relying on it.
- **concurrency** stops two deploys overlapping, which is how half-migrated databases are made.
- **permissions: contents: read** gives the workflow the least access it needs. Do not give CI more.
- **Watch paths.** For a repository that holds more than one deployable thing, Dokploy can limit a service to rebuild only when certain folders change. That avoids rebuilding the backend because someone edited the README.

## Verifying Every Deploy

"The deploy finished" does not mean "the site works". The smoke test checks, from the outside, the things that break most often after a deploy: the HTTP to HTTPS redirect, the readiness endpoint, and the security headers from Chapter 17.

**bash terminal (your laptop or CI)**

```bash
python3 -m dokploycheck.smoke --app https://app.example.com --api https://api.example.com
python3 -m dokploycheck.smoke --app https://app.example.com --api https://api.example.com --wait 600   # retry while the new version starts
```

**text what a healthy deploy prints (the format is verified; the addresses are yours)**

```text
[PASS] redirect app.example.com: http redirects to https://app.example.com/
[PASS] redirect api.example.com: http redirects to https://api.example.com/
[PASS] ready api.example.com: 200 OK
[PASS] header strict-transport-security app.example.com: present
[PASS] header x-content-type-options app.example.com: present
[PASS] header strict-transport-security api.example.com: present
[PASS] header x-content-type-options api.example.com: present
```

The exit code is 1 when anything fails, so CI marks the run red. With --wait, it retries every ten seconds until the checks pass or the time runs out, which covers the minute while the new containers start. Certificate expiry is checked by the script from Chapter 53 (python3 -m vpscheck.audit --certs app.example.com api.example.com).


## Rollbacks and Zero Downtime › Zero downtime with Applications

Dokploy’s **Applications** run as Docker Swarm services, and they can use **health checks and rolling updates**: the new container starts first, must pass its health check, and only then does traffic switch and the old container stop. If the new one never becomes healthy, the old one keeps serving. Applications can also keep **rollback images**, so you can return to a previous version from the panel. Dokploy’s documentation describes the requirements for each feature (for example a health check that its own tooling can run, and, for rollbacks, that images be kept), so read the pages on health checks and rollbacks for your version.

The pattern that gives you both is to **build in CI and deploy images**:

1. GitHub Actions runs the tests, builds the backend and frontend images, and pushes them to a registry (GitHub’s container registry works) tagged with the commit hash, such as chat-backend:3f9a2c1. Never rely on :latest, because it hides which version is running.
2. In Dokploy, create **Applications** for chat-api and chat-web with the Docker image source, a health check on /health/live, and the start-first update behaviour.
3. CI tells Dokploy to deploy the new tag. If the health check fails, traffic never moves.
4. Keep the workers (chat-worker, chat-beat, chat-channels) on the same tag, deployed in the same workflow.
You can do this one service at a time. A sensible path for a growing product is: start with the single Compose project of this chapter, move the API and web app to Applications when your users start to notice redeploy gaps, and leave the rest.

> **Celery Beat and WebSockets during deploys**
>
> Never run two Celery Beat containers, even briefly: a rolling update that starts a second scheduler before stopping the first runs every periodic task twice. Keep Beat in the Compose project with a stop-first update. Also remember that every deploy **closes open WebSockets**: clients must reconnect automatically, with a short random delay so that thousands of clients do not reconnect in the same second.


## Using AI Assistants for Deployment Work

Deployments produce long logs, and an AI assistant is good at reading them. The rules from Chapter 53 still apply, with two additions.

- **Paste logs, not environments.** Build and container logs are fine to share after you remove tokens, passwords and personal data. The Environment tab, .env files and database URLs are not. Read the log yourself first for lines that contain a URL with a password in it.
- **Ask for the first error, not a fix.** "Here is the build log. Which line is the first real error, and what does it mean?" teaches you something. A request for "fix it" produces confident changes to files you did not read.
- **Never give an assistant the panel’s API key,** the SSH key or a login to the panel. If you use Claude Code on the repository (Chapter 50), keep it on the code and the compose file, and run anything that touches the server yourself.
**text prompt template**

```text
Here is the deployment log from Dokploy for a Docker Compose project (Django ASGI, Celery,
Next.js). Secrets are removed. Find the FIRST error, explain what it means in plain language,
list the 3 most likely causes in order, and for each give a command I can run to check it.
Do not suggest changes to production data.
```
