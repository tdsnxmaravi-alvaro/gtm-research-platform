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
backend/                 # Django + DRF API
frontend/                # React + Vite wizard (campaigns, settings, progress)
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

Python 3.12+ (CI runs 3.13 and 3.14). Prefer the editable install so `extract-msg`
(Outlook `.oft` templates) is included:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env   # then fill in keys
pytest -q
```

`requirements.txt` is the same core set (including `extract-msg`) if you are not
installing the package as editable.

## Backend API (Django + DRF)

HTTP wrapper over the `gtm` engine. Config comes from environment variables;
SQLite locally, Postgres via `DATABASE_URL`. Pipeline stages run in a **background
thread** in local dev (`CELERY_TASK_ALWAYS_EAGER=true` or `RUN_STAGES_IN_THREAD=true`).
Docker Compose uses Celery `.delay()` so the `worker` service runs the pipeline.

## Running the servers

The app is **two servers**: the Django API and the Vite/React web app. Run both.

### Development (local, no Docker)

Backend — from the repo root:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pip install -r backend/requirements.txt
$env:CELERY_TASK_ALWAYS_EAGER = "true"    # background thread — no Redis needed
$env:GTM_DATA_ROOT = "$PWD\campaigns"     # campaign results/state/caches
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

There is **no application login** in this codebase (intended for local / trusted
network use). Do not expose the API to the public internet as-is.

Endpoints (`/api/`): `campaigns` (CRUD), `campaigns/{id}/validate`,
`.../start`, `.../research`, `.../enrich`, `.../consolidate`, `.../outreach`,
`.../results`, `.../contacts`, and `runs/{id}` for status.

### Docker / production-shaped stack

```powershell
copy .env.example .env
docker compose up -d --build
```

That starts `web` (Django/gunicorn), `worker` (Celery), `redis` and `postgres`,
mounting host `campaigns/` as `GTM_DATA_ROOT`. Set `DJANGO_SECRET_KEY` and
`DJANGO_ALLOWED_HOSTS` in `.env` before using this outside a laptop.

## Outreach templates

Branded Outlook `.oft` files are **optional**. Point `GTM_TEMPLATES_DIR` at a
folder of vendor templates (Bricsys, Dassault/DraftSight, Novade, Newforma,
Unity, Trimble). If none are present, outreach falls back to the built-in HTML
frame (and the OFT unit test skips).

Override per campaign by uploading a **custom header/logo** in the wizard (or
your own `.eml`); custom always wins over a vendor default.

## Status

| Phase | Scope | Status |
|---|---|---|
| 0 | Scaffold + config schema + provider interface | Done |
| 1 | Prompts + ingest + deterministic scoring + research runner + CLI | Done |
| 2 | Enrichment (Apollo emails/phones + LARA web-search agent) | Done |
| 3 | Consolidate master list + outreach (`.eml`) | Done |
| 4 | Django + DRF API | Done (local; no auth) |
| 5 | React wizard UI | Done (local wizard + campaign list) |

Roadmap and GitHub issue inventory (open vs closed) are in
[docs/next-steps.md](docs/next-steps.md) (for engineers and LLMs).
CI runs the test suite on every push/PR (badge above).
