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
campaigns/               # per-campaign yaml configs (+ runtime data, gitignored)
backend/                 # Django + DRF API (added after the core is validated)
frontend/                # React + Vite web app / wizard (later phase)
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # then fill in keys
pytest -q
```

## Status

Phase 0 (scaffold + config schema + provider interface). CLI core first; Django/React later.
