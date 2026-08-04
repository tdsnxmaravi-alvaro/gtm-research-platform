# GTM Research Platform — Architecture

Config/wizard-driven platform to **research → qualify → enrich → reach out** to target
companies (resellers or end-user accounts), for a chosen product/vendor and market.

- **Frontend:** React + Vite SPA
- **Backend:** Django + DRF (Celery in prod, background thread in dev)
- **Engine:** `gtm/` Python package (research, consolidate, enrichment, outreach)
- **External:** LARA assistants (web search), Apollo.io (contacts), Azure OpenAI (optional)
- **Storage:** SQLite (dev) / Postgres (prod) for metadata; disk artifacts under `GTM_DATA_ROOT`

---

## 1. System architecture (components & layers)

```mermaid
flowchart TB
    subgraph Client["Frontend — React + Vite SPA"]
        WZ["Wizard.jsx<br/>(campaign setup: target, list upload,<br/>column mapping, prompt, enrich, outreach)"]
        CMP["Campaigns.jsx<br/>(start/pause/stop, live progress,<br/>results, downloads)"]
        APIJS["api.js<br/>(REST client)"]
    end

    subgraph Backend["Backend — Django + DRF"]
        VS["CampaignViewSet<br/>(validate, start, stop, pause, status,<br/>runs, download, upload_list, remap_list,<br/>vendor_preset, previews)"]
        TASKS["tasks.py<br/>run_pipeline / run_stage<br/>(Celery task; local = background thread)"]
        MODELS["models.py<br/>Campaign · Run"]
    end

    subgraph Engine["Engine — gtm/ package"]
        RES["research/<br/>runner + prompts + providers<br/>(concurrent waves)"]
        CONS["consolidate/<br/>master.py (CSV + multi-sheet XLSX)"]
        ENR["enrichment/<br/>apollo · lara_agent · cache · phones"]
        OUT["outreach/<br/>email_gen · runner · oft · eml"]
    end

    subgraph Ext["External services"]
        LARA["LARA assistants<br/>(research · enrich · schema-map ·<br/>outreach) + web search"]
        APOLLO["Apollo.io<br/>(people search, email + async phone reveal)"]
        AOAI["Azure OpenAI<br/>(optional research provider)"]
    end

    subgraph Store["Storage"]
        DB[("SQLite dev /<br/>Postgres prod")]
        FS[["GTM_DATA_ROOT (disk)<br/>results.csv · contacts.csv ·<br/>master.csv/xlsx · eml/ · caches"]]
    end

    WZ --> APIJS
    CMP --> APIJS
    APIJS -->|"/api (Vite proxy)"| VS
    VS --> MODELS
    VS --> TASKS
    MODELS --- DB
    TASKS --> RES --> CONS --> ENR --> OUT
    RES --> LARA
    RES --> AOAI
    ENR --> APOLLO
    ENR --> LARA
    OUT --> LARA
    RES <--> FS
    CONS <--> FS
    ENR <--> FS
    OUT <--> FS

    style Client fill:#e8f0fe,stroke:#4285f4
    style Backend fill:#e6f4ea,stroke:#34a853
    style Engine fill:#fef7e0,stroke:#f9ab00
    style Ext fill:#fce8e6,stroke:#ea4335
    style Store fill:#f3e8fd,stroke:#a142f4
```

---

## 2. Pipeline flow (research → consolidate → enrich → outreach)

The pipeline runs stage by stage. Each stage is **resumable** (state saved to disk) and
**cancelable** (a `control.json` flag is checked between batches/stages).

```mermaid
flowchart LR
    A["Provided list (.xlsx/.csv)<br/>or Discover (verticals)"] --> B

    subgraph P["Pipeline (resumable · cancelable)"]
        direction LR
        B["1 · RESEARCH<br/>per-company web-search scoring<br/>(evidence-gated tiers)<br/>+ employees/software/independence"]
        C["2 · CONSOLIDATE<br/>dedupe + tier filter →<br/>shortlist master"]
        D["3 · ENRICH<br/>contacts (email/phone)<br/>Apollo or LARA<br/>→ refresh master"]
        E["4 · OUTREACH<br/>email + follow-up +<br/>talking points → .eml drafts"]
        B --> C --> D --> E
    end

    B -. cache .-> RC[(".gtm_cache/research.json")]
    D -. cache .-> CC[(".gtm_cache/contacts.json")]
    C --> MX[["master.xlsx<br/>Master Outreach · All Contacts"]]
    E --> MX2[["master.xlsx + Outreach tab"]]
    E --> EML[["eml/ drafts (branded .oft)"]]

    style P fill:#fef7e0,stroke:#f9ab00
```

> **Evidence-gated scoring:** without a verifiable source URL, a company cannot exceed the
> capped tier. **Concurrency:** in provided mode, research batches run in parallel waves
> (`research_concurrency`, default 3).

---

## 3. Enrichment provider logic (LARA ↔ Apollo upgrade rule)

Provider priority: **Apollo (1) > LARA (0)**. A higher-priority provider re-visits companies
already enriched by a lower-priority one, but **only overwrites when it actually finds
contacts**; otherwise the existing contacts are kept. Same-or-lower priority reuses the cache
(no re-charge, no downgrade). The contact cache is keyed by **domain** and shared across
campaigns.

```mermaid
flowchart TD
    S["Shortlist company<br/>(from master.csv)"] --> Q{"In cache /<br/>already done?"}
    Q -->|"cached rank at or above current"| REUSE["Reuse cached contacts<br/>(no re-charge, no downgrade)"]
    Q -->|"no, or lower-rank LARA and<br/>current = Apollo"| FETCH["Fetch with current provider"]

    FETCH --> PROV{"Provider"}
    PROV -->|Apollo| AP["people search + email reveal<br/>(+ async phone reveal, +8 cr)"]
    PROV -->|LARA| LA["web-search contacts<br/>(+ public phone if found)"]

    AP --> R{"Found contacts?"}
    LA --> R
    R -->|Yes| WIN["Replace prior contacts<br/>(Apollo supersedes LARA)"]
    R -->|"No (upgrade attempt)"| KEEP["Keep existing LARA contacts"]

    WIN --> W[["Write contacts.csv +<br/>cache + build_master"]]
    KEEP --> W
    REUSE --> W

    style AP fill:#fce8e6
    style LA fill:#e8f0fe
```

> **Phones are asynchronous** (Apollo reveal, ~40 min via webhook/poll). A single pipeline run
> fires reveals but does not wait; re-run enrich (or run the webhook receiver) to merge numbers.
> **Talking points** are only generated for contacts whose phone number was obtained.

---

## 4. On-disk artifacts per campaign

```mermaid
flowchart TB
    subgraph Camp["GTM_DATA_ROOT / campaign folder"]
        R1["results.csv<br/>(scored companies)"]
        C1["contacts.csv<br/>(enriched contacts)"]
        M1["master.csv (contact-level)"]
        M2["master.xlsx<br/>(Master Outreach · All Contacts · Outreach)"]
        E1["eml/*.eml (drafts)"]
        ST["state: research_state · enrich_state ·<br/>phone_reveals · enrich_credits · control.json"]
    end
    subgraph Shared["GTM_DATA_ROOT/.gtm_cache/ (shared)"]
        RC["research.json<br/>(vendor|type|product|domain)"]
        CC["contacts.json<br/>(by domain)"]
    end
    subgraph Tpl["GTM_TEMPLATES_DIR + .templates/"]
        OFT["vendor .oft templates"]
        EMLT["generated .eml frames"]
    end

    R1 --> M1 --> M2
    C1 --> M1
    M2 --> E1
    R1 -.-> RC
    C1 -.-> CC
    OFT --> EMLT --> E1
```

---

## Deployment

| | Dev | Prod |
|---|---|---|
| Web | `manage.py runserver` | Django (docker-compose `web`) |
| Task execution | background thread (`RUN_STAGES_IN_THREAD`) | Celery worker + Redis broker |
| Database | SQLite (`db.sqlite3`) | Postgres (`DATABASE_URL`) |
| Data root | `backend/data` or `campaigns/` | `/data` volume (`GTM_DATA_ROOT`) |

## External AI assistants (LARA)

| Purpose | Env assistant id | Web search |
|---|---|---|
| Research / scoring | `LARA_RESEARCH_ASSISTANT_ID` | on |
| Contact enrichment | `LARA_ENRICHMENT_ASSISTANT_ID` | on |
| Schema (column) mapping | `LARA_SCHEMA_ASSISTANT_ID` | off |
| Outreach copy | `LARA_OUTREACH_ASSISTANT_ID` | off |
