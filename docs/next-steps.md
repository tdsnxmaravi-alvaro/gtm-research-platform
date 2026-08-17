# GTM Research Platform — Issue inventory and next steps

**Audience:** any engineer or LLM picking up this repo with no prior chat history.

**Repo:** https://github.com/tdsnxmaravi-alvaro/gtm-research-platform  
**Snapshot date:** 2026-08-17  
**Default branch:** `main` (P1 export/resume work ships with this file; reliability baseline: `da85348`)

Read this file **before** creating GitHub issues or starting a new feature. Duplicate issues have already happened historically (phases 1–5 vs later wizard tickets). Backlog tickets **#22–#38** were created on 2026-08-17. Do not open copies.

Related docs:

- [README.md](../README.md) — what the product is, how to run it locally
- [docs/architecture.md](architecture.md) — pipeline, layers, on-disk artifacts
- [docs/lara-integration.md](lara-integration.md) — LARA assistants

---

## 1. What this project is (one paragraph)

Config-driven **go-to-market research engine** for TD SYNNEX / Datech: qualify companies (resellers or end-user accounts) for a vendor/product, enrich decision-maker contacts (Apollo.io and/or LARA web search), consolidate a master list, generate branded `.eml` drafts. The Python package `gtm/` is the engine (CLI: `python -m gtm`). `backend/` is Django+DRF. `frontend/` is a React+Vite wizard. **There is no authentication in the API** — local / trusted-network use only.

Pipeline (always this order in the API): **research → consolidate → enrich → outreach**. Each stage writes files under `GTM_DATA_ROOT/<campaign-name>/` (`results.csv`, `contacts.csv`, `master.csv`/`master.xlsx`, `eml/`, `state.json`, `enrich_state.json`, `phone_reveals.json`). Shared caches live in `GTM_DATA_ROOT/.gtm_cache/`.

---

## 2. How to use this document

| If you are… | Do this |
|-------------|--------|
| Creating GitHub issues | Skip §3–§5 (already on GitHub: #5 and #31–#38 open; #22–#30 and #39–#44 closed). |
| Implementing | Prefer §6 ordered backlog. Do not re-implement §4. Do not start #33–#38 (P4) unless a maintainer asks. |
| An LLM | Treat file paths as source of truth. `git log -1 da85348` is the reliability patch. **#22–#30** are done. Open work is **#5** plus **#31–#32**; **#33–#38** wait. |

**Labels to use on new issues:** `bug`, `enhancement`, `documentation`. Language: **English** for titles, bodies, commits, and code comments.

---

## 3. Issues that already exist on GitHub

### 3.1 Open (do not duplicate)

| # | Title | Notes |
|---|--------|--------|
| [#5](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/5) | Multi-LLM ensemble research with Azure AI Foundry models | **Still open.** Partial code exists (`research_providers`, `gtm/providers/azure_foundry.py`, averaging in `gtm/research/runner.py`). The **design blocker remains**: Foundry chat models often have **no web search**, so they invent scores and get capped by the URL evidence gate. Issue body recommends (A) Foundry agents with grounding, or (B) LARA gathers evidence then a panel of models scores that evidence. Do not close until one of those is done and documented. |
| [#31](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/31)–[#32](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/32) | P3 backlog | Created 2026-08-17. Details in §5. |
| [#33](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/33)–[#38](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/38) | P4 later / security | Created 2026-08-17. **Do not start** until a maintainer asks. |

### 3.2 Closed (historical — treat as done unless you find a regression)

These are **closed on GitHub**. They describe the original build-out. Closing them does **not** mean every follow-up from the 2026-08 code review is done.

| # | Title | What “done” means in the codebase |
|---|--------|-----------------------------------|
| [#1](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/1) | Phase 2 — Enrichment (Apollo + LARA agent) | `gtm/enrichment/` Apollo + LARA paths |
| [#2](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/2) | Phase 3 — Consolidate + Outreach (`.eml`) | `gtm/consolidate/`, `gtm/outreach/` |
| [#3](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/3) | Phase 4 — Django + DRF API | `backend/api/` ViewSets, Celery-shaped tasks |
| [#4](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/4) | Phase 5 — React wizard UI | `frontend/src/Wizard.jsx`, `Campaigns.jsx`, `Settings.jsx` |
| [#6](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/6) | Outreach GUI visual template builder | Branded `.eml` / `.oft` path exists; **not** a full visual template editor |
| [#7](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/7) | Wizard: field validation + step gating | Wizard `stepError` / `next` |
| [#8](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/8) | Wizard: vendor as controlled dropdown | Vendor presets in wizard |
| [#9](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/9) | Wizard: field UX (outreach, tiers, sender, providers) | Sender inputs are on the Outreach step (#27) |
| [#10](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/10) | Wizard: friendly Review step | Review step in `Wizard.jsx` |
| [#11](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/11) | Ingest: Excel upload + column mapping | `upload_list` / `remap_list` + `gtm/ingest/` |
| [#12](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/12) | Wizard: prompt builder | `preview_prompt` + prompt step |
| [#13](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/13) | EPIC: Discover mode verticals + Datech countries | Parent of #14–#17 |
| [#14](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/14) | Vertical presets + vendor×vertical map + exclusions | `gtm/prompts/vertical_presets.py` |
| [#15](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/15) | Discover prompt builder | `gtm/prompts/builder.py` discover templates |
| [#16](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/16) | Wizard discover UI | Vertical + country pickers |
| [#17](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/17) | Datech country list + multi-country execution | `DATECH_COUNTRIES`, `config.countries` |
| [#18](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/18) | Regenerate vendor-landscape via multi-LLM | `gtm/tools/gen_landscape.py` + overlay JSON |
| [#19](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/19) | Relaunch + global Apollo contact cache | `relaunch` / `ContactCache` |
| [#20](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/20) | Provider CRUD in Settings | `ProviderSetting` + `Settings.jsx` |
| [#21](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/21) | Auto-manage Apollo webhook tunnel | `backend/api/phone_delivery.py` + cloudflared |

Reliability work from August 2026 is commit `da85348` and closed issues **#39–#44**. P1 (**#22–#25**) is implemented. **#26–#30** are done. Active backlog is **#5** plus **#31–#38**.

---

## 4. Work already on `main` (closed GitHub issues #39–#44)

Implementations are in commit **`da85348`** (*Persist billed Apollo contacts and harden local pipeline resume.*). Tests at that commit: `pytest` → 121 passed.

**Do not re-implement these.** Created 2026-08-17 and closed as `completed`, linking `da85348`.

### [#39](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/39) — Persist billed Apollo contacts before credit-exhaustion stop

- **Type:** bug (fixed)
- **Files:** `gtm/enrichment/runner.py`, `tests/test_phase2.py` (`test_run_enrichment_persists_contacts_when_exhausted`)
- **Was:** `break` on `apollo_client.exhausted` **before** writing contacts/cache/state → double-charge on resume; log said “nothing lost”.
- **Now:** persist `got` / cache / `enrich_state.json` / `contacts.csv` first; empty+exhausted does **not** mark the company done; remaining companies are not processed in that pass.

### [#40](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/40) — Atomic JSON writes for resume state

- **Type:** bug (fixed)
- **Files:** `gtm/io.py` (`atomic_write_json`), `gtm/enrichment/runner.py` `_save_done`, `gtm/research/runner.py` `_save_state`, `gtm/research/cache.py`, `tests/test_io.py`
- **Was:** in-place `write_text` of `state.json` / `enrich_state.json` (crash → corrupt checkpoint → full re-run).
- **Now:** temp file + `replace()`.

### [#41](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/41) — Apollo HTTP retries, retryable phone reveals, strict preflight

- **Type:** bug (fixed)
- **Files:** `gtm/enrichment/apollo/client.py`, `gtm/enrichment/apollo/phones.py`, `.env.example` (`APOLLO_PREFLIGHT_STRICT`), `tests/test_phase2.py`
- **Was:** single HTTP attempt; 429/5xx marked `error`/`is_attempted` forever; preflight **proceeded** if usage stats HTTP ≠ 200.
- **Now:** `requests.Session` + urllib3 `Retry` on 429/502/503/504; 429/5xx on reveal **not** marked attempted (pass stops); preflight **fail-closed** unless `APOLLO_PREFLIGHT_STRICT=false`.

### [#42](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/42) — Cross-process file locks + no phone numbers in webhook logs

- **Type:** bug (fixed)
- **Files:** `gtm/io.py` (`file_lock`), `gtm/enrichment/cache.py`, `gtm/enrichment/apollo/phones.py`, `gtm/enrichment/apollo/webhook.py`
- **Was:** in-process `threading.Lock` only; webhook `print`ed raw phone numbers.
- **Now:** OS lock (`msvcrt` / `fcntl`) around JSON saves; webhook logs **count** of phones, not values.

### [#43](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/43) — README matches the code

- **Type:** documentation (fixed)
- **Files:** `README.md`, `requirements.txt` (`extract-msg`), `.gitignore` (`campaigns/_uploads/`)
- **Was:** `pip install -r requirements.txt` omitted `extract-msg`; claimed `templates/` is committed/required (it is not); duplicate setup block; phases 4–5 called “scaffold”.
- **Now:** `pip install -e ".[dev]"`; templates optional via `GTM_TEMPLATES_DIR`; API/wizard marked done for **local** use.

### [#44](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/44) — Tests: outreach runner, CLI, negated competitor scoring

- **Type:** enhancement (fixed)
- **Files:** `tests/test_phase3.py` (`test_run_outreach_writes_eml`), `tests/test_cli.py`, `gtm/scoring/engine.py` (`_negated_competitor`), `tests/test_phase1.py` (`test_discover_gate_ignores_negated_competitor`)
- **Was:** no `run_outreach` / CLI tests; “not an Autodesk Gold partner” still capped as locked.
- **Now:** those tests exist; negation skips the competitor lock cue.

**GitHub issues (closed as completed):** [#39](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/39)–[#44](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/44).

---

## 5. Backlog on GitHub (created 2026-08-17)

These are **open** issues. Do not recreate them. Grouped by priority.

Context agreed with maintainers (2026-08): **local / small-team first**. Auth and production hardening are **later**, not ignored.

---

### P1 — Engine correctness / money (**done**, closed #22–#25)

#### [#22](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/22) — CSV formula injection on master.xlsx / CSV exports — **done**

**Labels:** `bug`  
**Files:** `gtm/consolidate/master.py` (`_write_csv`, `_fill_sheet`), `gtm/ingest/parser.py` (`write_rows_csv`)

LLM and spreadsheet fields (`fit_summary`, `notes`, company names) are written raw. Excel treats leading `=`, `+`, `-`, `@` as formulas. `master.xlsx` is opened by BDRs.

**Acceptance:** one `csv_safe()` helper; prefix a quote on those leading characters at every export path; unit test with `=HYPERLINK(...)`.

---

#### [#23](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/23) — CRLF stripping on `.eml` headers — **done**

**Labels:** `bug`  
**Files:** `gtm/outreach/eml.py` `write_eml`

`Subject` / `From` / `To` come from CSV + LLM. Newlines in a subject are header injection when Outlook opens the draft.

**Acceptance:** strip `\r`/`\n` and cap length before assigning headers; test with a subject containing `\r\n`.

---

#### [#24](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/24) — Index Datech fuzzy matching (O(n×m) → blocked match) — **done**

**Labels:** `enhancement`  
**Files:** `gtm/consolidate/datech_match.py` `DatechIndex.find`, `gtm/consolidate/master.py` `_annotate_datech`

Per company: full scan of the invoicing list + `SequenceMatcher` (slow on FY invoicing CSVs). Two different normalizers (`normalize_name` vs `normalize_for_match`) disagree.

**Acceptance:** inverted token index / blocking key; one shared normalizer; test that “Acme SL” and “ACME, S.L.” still match; document `DEFAULT_DATECH_CSV` (FY22 path is hardcoded).

---

#### [#25](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/25) — Do not rewrite contacts.csv after every company (checkpoint every N) — **done**

**Labels:** `enhancement`  
**Files:** `gtm/enrichment/runner.py`, `gtm/research/runner.py`

Full CSV rewrite per company is O(n²) I/O. Acceptable for small lists; painful at 1k+ companies.

**Acceptance:** append or rewrite every N companies + always on cancel/exhaust/end; tests still see a complete file after a run.

---

### P2 — Local pipeline / API behavior

#### [#26](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/26) — Dispatch pipeline through Celery `.delay()` (threads are not the worker) — **done**

**Labels:** `bug`  
**Files:** `backend/api/views.py` `_run_bg`, `backend/api/tasks.py` `run_pipeline`, `backend/gtm_api/settings.py`

`run_stage` is `@shared_task` but **nothing calls `.delay()`**. `_run_bg` always starts a **daemon thread**. Docker `worker` service idles. Deploys/gunicorn recycle kill in-flight runs. Two `POST /start` can race on the same files.

**Acceptance:** `run_pipeline` is a task; production uses `.delay()`; local uses thread only when `RUN_STAGES_IN_THREAD` / eager is set; one in-flight run per campaign (reject or queue); tests still pass with `TESTING` synchronous path.

---

#### [#27](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/27) — Wizard sender fields + email preview sandbox — **done**

**Labels:** `bug`  
**Files:** `frontend/src/Wizard.jsx` (Outreach step, `srcDoc` iframe ~line 874)

`sender_name` / `sender_email` never appear as inputs (only hydrate/Review). Preview iframe has no `sandbox` attribute (`srcDoc` is same-origin).

**Acceptance:** Outreach step inputs wired to `buildConfig`; iframe `sandbox=""` (preview needs no script); AbortController or ignore stale `remapList` responses.

---

#### [#28](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/28) — Campaigns.jsx polling leaks — **done**

**Labels:** `bug`  
**Files:** `frontend/src/Campaigns.jsx` `poll` / `pollPipeline`

`setInterval` is not cleared on unmount; repeat Start stacks intervals; `setState` after unmount.

**Acceptance:** one interval per campaign in a ref; `clearInterval` in `useEffect` cleanup; no interval after leaving the list tab.

---

#### [#29](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/29) — Discover-mode research concurrency — **done**

**Labels:** `enhancement`  
**Files:** `gtm/research/runner.py` discover loop (~countries × products × verticals)

Provided mode uses `ThreadPoolExecutor` waves (`research_concurrency`). Discover is fully serial + `sleep`. Multi-country Datech lists become very slow.

**Acceptance:** bounded concurrency for discover keys with the same cancel/checkpoint semantics; document rate-limit risk.

---

### P3 — Tests, tooling, maintainability

#### [#30](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/30) — Tests for untested orchestration — **done**

**Labels:** `enhancement`  
**Files:** `gtm/cli.py` (beyond validate/estimate), `backend/api/views.py` (upload, download, enrich/outreach actions), `backend/api/tasks.py` `run_stage` / `run_pipeline` (not only mocked)

**Acceptance:** Django tests for `upload_list` (size/ext), `download` allowlist, `start` creates a Run; engine test that `run_pipeline` order is research→consolidate→enrich→outreach when want≠none.

---

#### [#31](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/31) — ruff + dependency lockfile + CI lint

**Labels:** `enhancement`  
**Files:** `pyproject.toml`, `.github/workflows/ci.yml`

All Python deps are `>=` unpinned. No ruff/eslint in CI. Frontend has `eslint-disable` comments but no ESLint installed.

**Acceptance:** `ruff check` job; lockfile (`uv lock` or pip-tools) used in CI; optional eslint on `frontend/`.

---

#### [#32](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/32) — Parameterize “TD SYNNEX / Datech” copy; move vendor presets to data files

**Labels:** `enhancement`  
**Files:** `gtm/outreach/email_gen.py`, `gtm/prompts/vendor_presets.py`, `gtm/prompts/vertical_presets.py`

Distributor name and ~900 lines of vendor data are Python literals. Onboarding a vendor requires a code change.

**Acceptance:** org name from config/env; vendor/vertical YAML or JSON loaded at runtime (overlay already exists for landscape brands).

---

### P4 — Later (when the app is not local-only)

Do **not** start these until a maintainer asks. They are the 2026-08 security review.

| # | Title | Why it waits | Files |
|---|--------|--------------|--------|
| [#33](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/33) | DRF `IsAuthenticated` + campaign owner | No login by design for local use | `backend/gtm_api/settings.py`, `views.py`, `frontend/src/api.js` |
| [#34](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/34) | Fail-closed Django secrets (`DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`) | Docker compose still uses `ALLOWED_HOSTS=*` | `settings.py`, `docker-compose.yml` |
| [#35](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/35) | Webhook HMAC + localhost bind + tunnel opt-in | Auto cloudflared is a product feature for non-technical users | `webhook.py`, `phone_delivery.py` |
| [#36](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/36) | Allowlist `ProviderSetting.endpoint_url` (SSRF) | Writable endpoint + API key sent there | `serializers.py`, `gtm/providers/factory.py` |
| [#37](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/37) | Dockerfile non-root user + templates volume | Container hardening | `Dockerfile` |
| [#38](https://github.com/tdsnxmaravi-alvaro/gtm-research-platform/issues/38) | Prompt-injection fencing for uploaded company names | Untrusted Excel → LLM prompt | `gtm/prompts/builder.py` `format_companies` |

---

## 6. Recommended implementation order (for the next programmer / LLM)

Do **not** start with P4 unless the deployment target changes.

1. **#5** (existing) — decide A vs B for ensemble web-search; implement; close #5.  
2. **#31** tooling, **#32** vendor data extraction.

**Done:** #22–#30.

---

## 7. Constraints for implementers

- **Language:** English for issues, commits, comments, user-facing docs.
- **Do not** add auth “while you’re here” without an explicit request.
- **Do not** force-push `main`.
- **Do not** commit `.env`, `campaigns/_uploads/`, logos, or `.oft` binaries unless the team decides templates belong in git.
- Secrets stay as **env var names** in config (`api_key_env`), never inline keys.
- Enrichment cache is **by domain** and shared across campaigns; Apollo must not be re-charged for a cached domain unless a higher-priority provider finds new contacts (`gtm/enrichment/runner.py` provider rank).
- Scoring totals are **summed in Python** from per-dimension points, not a holistic LLM score (`gtm/ingest/parser.py` / `gtm/research/runner.py` `_aggregate_passes`).
- Evidence rule: no verified URL → tier capped (`gtm/scoring/engine.py` `apply_url_gate`).

---

## 8. Quick map: closed vs create vs skip

```text
GitHub CLOSED:  #1–#4, #6–#21, #22–#30, #39–#44
GitHub OPEN:    #5, #31–#32 (do these); #33–#38 (P4, wait)
SKIP:           re-doing enrichment/wizard phases; duplicating #5/#22–#44; implementing P4 unasked
```

---

## 9. Verification commands

```powershell
pip install -e ".[dev]"
pytest -q
pip install -r backend/requirements.txt
python backend\manage.py test
```

Frontend: `cd frontend; npm ci; npm run build` (no unit tests exist).
