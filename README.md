# GTM Research Platform

[![CI](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.13%20%7C%203.14-blue)
![License](https://img.shields.io/badge/license-internal-lightgrey)

Config-driven platform to **qualify target companies for a product, enrich their
contacts, and generate ready-to-send outreach** — for two audiences:

- **Resellers** — does the company fit to *sell* the product? (channel recruitment)
- **Accounts / end-users (leads)** — does the company fit to *buy/use* the product? (demand)

It generalizes an earlier multi-vertical BricsCAD pipeline and the Copilot Studio
lead-qualifier into one engine. Copilot Studio stays as the interactive shortcut;
this platform is the bulk / campaign engine (qualify → enrich → consolidate → outreach).

## Core ideas

- **One campaign config per project** (`campaigns/<name>.yaml`) drives everything.
- **`target_type`** (`accounts` | `resellers`) selects the qualification prompt family,
  fit criteria, scoring and outreach messaging. Everything else is shared plumbing.
- **`mode`** (`discover` | `provided`) — find companies vs qualify a given list.
- **`country`** is global and drives prompts, Apollo geo, enrichment and outreach language.
- **Evidence-required**: every key claim needs a source URL, else `UNVERIFIED`
  (hard rule: no verified URL → capped tier).

### Valid combinations (enforced by the config validator)

| target_type | mode              | verticals            | valid |
|-------------|-------------------|----------------------|-------|
| resellers   | discover          | optional (broad/list)| ✅    |
| resellers   | provided          | none                 | ✅    |
| accounts    | provided          | none                 | ✅    |
| accounts    | discover (broad)  | none                 | ✅    |
| accounts    | discover per-vert | —                    | 🚫    |
| any         | provided + verticals | —                 | 🚫    |

> Golden rule: **verticals only exist in `discover`**; `provided` never has verticals;
> **accounts never have verticals**.

## Layout

```
gtm/                     # core Python package (CLI-runnable)
  config/schema.py       # campaign config models + conditional validation
  providers/             # LLM provider abstraction (LARA, Azure OpenAI, Manual)
  prompts/               # prompt builder (5 template families)
  ingest/                # parse LLM output + provided lists -> rows
  scoring/               # tiering + hard URL evidence gate
  research/              # research runner (discover / provided, resumable)
  enrichment/            # contact resolution: Apollo + LARA agent paths
campaigns/               # per-campaign yaml configs (+ runtime data, gitignored)
backend/                 # Django + DRF API (added after the core is validated)
frontend/                # React + Vite web app / wizard (later phase)
```

## CLI

```powershell
python -m gtm validate  campaigns/spain-bricscad.yaml
python -m gtm estimate  campaigns/spain-bricscad.yaml
python -m gtm run       campaigns/spain-bricscad.yaml --limit 6
python -m gtm enrich    campaigns/spain-bricscad.yaml --limit 6
```

### Deterministic scoring & run-to-run stability

Scoring is **anchored + deterministic**: the LLM scores each dimension against
explicit point-band anchors and returns per-dimension points; the total is summed
in Python (never a holistic LLM number). Dimensions are **universal** (reusable
across any vendor/vertical) plus **campaign-specific** ones, defined in the config.
For borderline companies that can swing between adjacent tiers, average multiple
research passes to cut variance (~1/√N):

```powershell
python -m gtm run campaigns/spain-bricscad.yaml --limit 20 --passes 3
```

Enrichment is driven by the config's `enrichment` block: `provider` (`apollo` |
`lara`) and `want` (`none` | `emails` | `emails+phones`). The Apollo path adds
async phone reveals (resumable, no double-charge); the LARA path resolves
contacts via web search with no Apollo credits.

### Phone reveals via webhook (cloudflared)

Apollo delivers phone numbers asynchronously. For the live callback path:

```powershell
# terminal 1 — receiver (writes campaigns/<name>/phone_reveals.json)
python -m gtm webhook campaigns/spain-bricscad.yaml
# terminal 2 — tunnel (no signup)
cloudflared tunnel --url http://localhost:8000
# .env  ->  APOLLO_WEBHOOK_URL=https://<tunnel-host>/apollo-webhook
# terminal 3 — run enrichment against the live webhook
python -m gtm enrich campaigns/spain-bricscad.yaml --webhook --poll-wait 3600
```

Without `--webhook`, enrichment recovers numbers by polling `webhook_result`
(no tunnel required).

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # then fill in keys
pytest -q
```

## Backend API (Django + DRF)

Thin HTTP wrapper over the `gtm` engine. Cloud-agnostic (12-factor): all config
comes from environment variables; SQLite locally, Postgres in the cloud via
`DATABASE_URL`; async pipeline stages via Celery + Redis (or run inline locally).

## Running the servers

The app is **two servers**: the **Django API** (backend) and the **Vite/React web
app** (frontend). Run both.

### Development (local, no Docker)

Backend — from the repo root:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e .                          # the gtm engine (+ extract-msg for templates)
pip install -r backend/requirements.txt
$env:CELERY_TASK_ALWAYS_EAGER = "true"    # run stages in a background thread — no Redis needed
$env:GTM_DATA_ROOT = "$PWD\campaigns"     # where campaign results/state/caches are written
python backend\manage.py migrate
python backend\manage.py runserver 127.0.0.1:8000
```

Frontend — in a second terminal:

```powershell
cd frontend
npm install
npm run dev            # http://localhost:5173  (proxies /api -> 127.0.0.1:8000)
```

Open http://localhost:5173. Optional provider keys go in `.env` (`LARA_*`,
`APOLLO_*`, `AZURE_OPENAI_*`); without them research/enrich/outreach use their
offline fallbacks.

> Restart `runserver` after editing Python so the new logic is loaded.

### Production

Run a real **Celery worker + Redis + Postgres**, serve the **built frontend** as
static assets, and run Django under a WSGI server. The committed
`docker-compose.yml` wires it all together:

```powershell
copy .env.example .env      # fill DATABASE_URL, CELERY_BROKER_URL, DJANGO_*, provider keys...
docker compose up -d --build
```

That starts `web` (Django/gunicorn), `worker` (Celery), `redis` and `postgres`,
mounting host `campaigns/` as `GTM_DATA_ROOT`. The manual (no-Docker) equivalent:

```powershell
# API (WSGI)
pip install -e . -r backend/requirements.txt gunicorn
python backend\manage.py migrate
python backend\manage.py collectstatic --noinput
gunicorn gtm_api.wsgi --chdir backend --bind 0.0.0.0:8000
# Worker (separate process) — needs CELERY_BROKER_URL pointing at Redis
celery -A gtm_api --workdir backend worker -l info
# Frontend — build once, serve frontend/dist behind your web server / CDN
cd frontend; npm ci; npm run build
```

Key production env vars: `DATABASE_URL`, `CELERY_BROKER_URL`, `GTM_DATA_ROOT`,
`DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, plus provider
keys. Leave `CELERY_TASK_ALWAYS_EAGER` **unset/false** in production so stages run
on the worker (not in the request).

## Outreach templates (`templates/`)

**Do not delete `templates/`.** It holds the per-vendor Outlook `.oft` branded
email templates (Bricsys, Dassault → DraftSight, Novade, Newforma, Unity, Trimble).
When a campaign's vendor matches one, its template is **auto-selected** for the
`.eml` drafts — the logo and BDR signature are preserved and the generated body is
injected. The folder is **required at runtime and committed to the repo**.

Override per campaign by uploading a **custom header/logo** in the wizard (or your
own `.eml`); custom always wins over the vendor default. Point at a different
folder with `GTM_TEMPLATES_DIR`.
via env vars, SQLite locally / Postgres via `DATABASE_URL` in the cloud.

```powershell
pip install -e .                       # install the engine
pip install -r backend/requirements.txt
cd backend
python manage.py migrate
python manage.py runserver
```

Endpoints (`/api/`): `campaigns` (CRUD), `campaigns/{id}/validate`,
`.../research`, `.../enrich`, `.../consolidate`, `.../outreach` (async, return a
`Run`), `.../results`, `.../contacts`, and `runs/{id}` for status.

**Deploy anywhere** with the root `Dockerfile` (gunicorn): Azure Container Apps /
App Service, AWS ECS/Fargate / App Runner, GCP Cloud Run. Managed Postgres
(Azure DB for PostgreSQL, AWS RDS) via `DATABASE_URL`.

## Status

| Phase | Scope | Status |
|---|---|---|
| 0 | Scaffold + config schema + provider interface | ✅ Done |
| 1 | Prompts + ingest + deterministic anchored scoring + research runner + CLI | ✅ Done |
| 2 | Enrichment (Apollo emails/phones + LARA web-search agent) | ✅ Done |
| 3 | Consolidate master list + outreach (`.eml`) | ✅ Done |
| 4 | Django + DRF API | 🚧 In progress (API scaffold + Docker done) |
| 5 | React wizard UI | 🚧 In progress (Vite + React scaffold) |

Roadmap is tracked in [GitHub Issues](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues).
CI runs the test suite on every push/PR (badge above).
