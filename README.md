# GTM Research Platform

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

Enrichment is driven by the config's `enrichment` block: `provider` (`apollo` |
`lara`) and `want` (`none` | `emails` | `emails+phones`). The Apollo path adds
async phone reveals (resumable, no double-charge); the LARA path resolves
contacts via web search with no Apollo credits.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # then fill in keys
pytest -q
```

## Status

Phase 0 (scaffold + config schema + provider interface) and Phase 1 (prompts +
ingest + scoring + research runner + CLI) done. Phase 2 (enrichment: Apollo +
LARA agent) in place. Django/React later.
