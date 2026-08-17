"""Enrichment runner — resolve contacts for qualified companies.

Picks the enrichment provider from the campaign config (apollo | lara), respects
`want` (none | emails | emails+phones) and `max_contacts`, and is resumable
per-company. Writes an enriched contacts CSV.

Apollo path:
    - emails: people search + person enrich
    - emails+phones: additionally fire async phone reveals, poll, and merge
LARA path:
    - web-search contact resolution (no Apollo credits); emails only
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from ..config.schema import (
    CampaignConfig, EnrichProvider, EnrichWant, apollo_locations_for,
)
from ..io import atomic_write_json, CsvCheckpoint, read_csv_dicts
from .models import EnrichedContact, CONTACT_COLS
from .apollo import (
    ApolloClient, enrich_company,
    PhoneRevealStore, fire_reveals, poll_reveals, merge_phones,
)
from .lara_agent import build_lara_enrichment_provider, enrich_company_lara

log = logging.getLogger(__name__)


def _load_rows(results_path: Path) -> list[dict]:
    return read_csv_dicts(results_path)


def _load_done(path: Path) -> set:
    if path.exists():
        try:
            return set(json.loads(path.read_text(encoding="utf-8")).get("done", []))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def _save_done(path: Path, done: set) -> None:
    atomic_write_json(path, {"done": sorted(done),
                             "updated": datetime.now().isoformat()})


def run_enrichment(
    config: CampaignConfig,
    rows: list[dict] | None = None,
    *,
    limit: int = 0,
    delay: float = 0.5,
    resume: bool = True,
    poll_wait: int = 0,
    poll_interval: int = 600,
    use_webhook: bool = False,
    use_cache: bool = True,
    max_reveals: int | None = None,
    out_dir: str | Path | None = None,
    min_tier: str | None = None,
    should_cancel=None,
    progress_cb=None,
) -> list[EnrichedContact]:
    """Enrich qualified companies. Returns the enriched contacts.

    A shared domain cache (`.gtm_cache/contacts.json`) reuses contacts already
    fetched in previous runs/campaigns, so we never re-charge Apollo for a
    company (or contact) already enriched.
    """
    enr = config.enrichment
    if enr.want == EnrichWant.none:
        log.info("Enrichment want=none — nothing to do.")
        return []

    out = Path(out_dir or (Path("campaigns") / config.name))
    if rows is None:
        # Prefer the consolidated shortlist (deduped + tier-filtered) so we only
        # enrich companies worth contacting; fall back to raw results.
        rows = _load_rows(out / "master.csv") or _load_rows(out / "results.csv")
    if not rows:
        log.info("No qualified rows to enrich (run research + consolidate first).")
        return []

    contacts_path = out / "contacts.csv"
    state_path = out / "enrich_state.json"
    done = _load_done(state_path) if resume else set()

    # Only enrich the shortlist worth contacting (tier >= min_tier) so we never
    # spend Apollo credits / LLM tokens on low-tier companies.
    _TIER_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "": 9}
    cap = _TIER_ORDER.get((min_tier or config.outreach.min_tier or "D").upper(), 9)

    def _row_tier(r: dict) -> str:
        return (r.get("final_tier") or r.get("tier") or "").upper()

    all_contacts: list[EnrichedContact] = []
    # Resume must ACCUMULATE: reload prior contacts so we append instead of
    # overwriting contacts.csv with only the current batch.
    if resume and contacts_path.exists():
        for row in _load_rows(contacts_path):
            all_contacts.append(
                EnrichedContact(**{k: row.get(k, "") for k in CONTACT_COLS}))

    from .cache import ContactCache
    from .domains import extract_domain
    # Anchor the cross-run cache to the data root (out.parent) so it is stable
    # regardless of the process CWD and shared across campaigns (never re-charge
    # Apollo for a domain already enriched).
    cache = ContactCache(path=out.parent / ".gtm_cache" / "contacts.json",
                         enabled=use_cache)
    cache_hits = 0

    # Provider priority: a higher-priority provider "upgrades" a company already
    # enriched by a lower-priority one — but ONLY if it actually finds contacts.
    # Apollo (verified emails/phones) supersedes LARA; if Apollo finds nothing we
    # KEEP the LARA contacts. Same-or-lower priority just reuses the cache, so we
    # never downgrade or re-charge for data we already have.
    _PROVIDER_RANK = {"lara": 0, "webhook": 0, "apollo": 1}
    cur_provider = enr.provider.value
    cur_rank = _PROVIDER_RANK.get(cur_provider, 0)

    def _rank_of(cs: list[EnrichedContact]) -> int:
        return max((_PROVIDER_RANK.get((c.source or "").lower(), 0) for c in cs),
                   default=-1)

    def _norm(s: str) -> str:
        return (s or "").strip().lower()

    def _drop_company(lst: list[EnrichedContact], company: str) -> list[EnrichedContact]:
        cl = _norm(company)
        return [c for c in lst if _norm(c.company) != cl]

    def _eligible(r: dict) -> bool:
        if _TIER_ORDER.get(_row_tier(r), 9) > cap:
            return False
        # Skip existing Datech partners to save Apollo credits (opt-out via config).
        if getattr(enr, "skip_datech_matches", True) and (r.get("datech_match") or "").strip():
            return False
        company = r.get("company")
        if company not in done:
            return True
        # Already enriched: revisit only to upgrade with a higher-priority provider
        # that might now find contacts the previous (lower-priority) provider missed.
        domain = extract_domain(r.get("website") or "")
        cached = cache.get(domain) if domain else None
        return bool(cached) and _rank_of(cached) < cur_rank

    pending = [r for r in rows if (r.get("company") or "").strip() and _eligible(r)]
    if limit:
        pending = pending[:limit]
    log.info("Enrich: %s companies | tier>=%s | pending %s | provider=%s | want=%s",
             len(rows), min_tier or config.outreach.min_tier, len(pending),
             cur_provider, enr.want.value)

    # Build the provider once (lazily — skip if everything is cached).
    apollo_client = None
    lara_provider = None

    def _ensure_provider():
        nonlocal apollo_client, lara_provider
        if enr.provider == EnrichProvider.apollo:
            if apollo_client is None:
                locations = enr.locations or apollo_locations_for(config.country)
                apollo_client = ApolloClient(seniorities=enr.seniorities, locations=locations)
            return
        if lara_provider is None:
            lara_provider = build_lara_enrichment_provider()

    # Pre-flight: verify the Apollo key + credits BEFORE spending, so an invalid
    # key or empty balance stops cleanly instead of a burst of 4xx + a partial run.
    if enr.provider == EnrichProvider.apollo and pending:
        _ensure_provider()
        ok, msg = apollo_client.preflight()
        log.info("Apollo preflight: %s", msg)
        if not ok:
            atomic_write_json(out / "enrich_credits.json", {
                "apollo_credits": 0, "exhausted": True, "preflight": msg,
                "updated": datetime.now().isoformat(),
            })
            return all_contacts

    checkpoint = CsvCheckpoint(contacts_path, CONTACT_COLS)

    def _contact_rows() -> list[dict]:
        return [c.to_row() for c in all_contacts]

    def persist(*, force: bool = False) -> None:
        if checkpoint.note(_contact_rows(), force=force):
            _save_done(state_path, done)

    def persist_now() -> None:
        checkpoint.flush(_contact_rows())
        _save_done(state_path, done)

    for _i, r in enumerate(pending, 1):
        if should_cancel and should_cancel():
            persist_now()
            log.info("canceled — stopping enrichment (state saved)")
            break
        if progress_cb:
            progress_cb(_i, len(pending))
        company = r.get("company")
        domain = extract_domain(r.get("website") or "")
        cached = cache.get(domain) if domain else None
        cached_src = (cached[0].source if cached else "") or "previous"

        # Reuse the cache when it already holds same-or-higher-priority contacts.
        if cached is not None and _rank_of(cached) >= cur_rank:
            all_contacts = _drop_company(all_contacts, company)
            all_contacts.extend(cached)
            done.add(company)
            persist()
            cache_hits += 1
            log.info("%s: %s contacts (cache)", company, len(cached))
            continue

        # Fetch with the current provider (a fresh company, or an upgrade attempt).
        try:
            _ensure_provider()
            if enr.provider == EnrichProvider.apollo:
                got = enrich_company(apollo_client, r,
                                     max_contacts=enr.max_contacts, delay=delay)
            else:
                got = enrich_company_lara(lara_provider, r,
                                          country=(r.get("country") or config.country),
                                          max_contacts=enr.max_contacts,
                                          language=config.language or "en")
        except Exception as exc:  # noqa: BLE001 - log & continue
            log.warning("enrich error for %s: %s", company, exc)
            continue

        exhausted = (enr.provider == EnrichProvider.apollo and apollo_client is not None
                     and apollo_client.exhausted)

        # Persist billed contacts BEFORE stopping on credit exhaustion, otherwise
        # resume re-enriches the same people and double-charges.
        all_contacts = _drop_company(all_contacts, company)
        if got:
            all_contacts.extend(got)
            if domain:
                cache.put(domain, got)
            log.info("%s: +%s contacts%s", company, len(got),
                     f" (upgraded from {cached_src})" if cached is not None else "")
            done.add(company)
            persist(force=True)
        elif cached is not None:
            all_contacts.extend(cached)
            log.info("%s: kept %s %s contacts (no %s contacts found)",
                     company, len(cached), cached_src, cur_provider)
            done.add(company)
            persist()
        elif not exhausted:
            # Genuine empty result (no people found) — do not retry forever.
            done.add(company)
            persist(force=True)

        if exhausted:
            persist_now()
            log.warning("Apollo out of credits after %r — %s contacts saved. "
                        "Top up and Start again to resume.",
                        company, len(got) if got else 0)
            break

    # Phone reveals (Apollo only, when requested). Ensure the Apollo client exists
    # even when nothing was pending (e.g. resuming phone reveals for contacts whose
    # emails were already enriched) so reveals can still fire/poll.
    if (enr.provider == EnrichProvider.apollo and enr.want == EnrichWant.emails_phones
            and all_contacts and apollo_client is None):
        _ensure_provider()
    if (apollo_client is not None and enr.want == EnrichWant.emails_phones
            and all_contacts and not apollo_client.exhausted):
        store = PhoneRevealStore(out / "phone_reveals.json")
        fired = fire_reveals(apollo_client, all_contacts, store, max_reveals=max_reveals)
        log.info("Phone reveals fired: %s (numbers arrive async ~40 min).", fired)
        start = time.time()
        if use_webhook:
            # A separate `gtm webhook` process owns store writes; we only read
            # here to avoid a cross-process read-modify-write race.
            log.info("Waiting for webhook callbacks (run `gtm webhook` + cloudflared).")
            while True:
                store.reload()
                n_pending = store.pending_count()
                n_resolved = len(store.data) - n_pending
                log.info("monitor: %s resolved, %s pending", n_resolved, n_pending)
                if n_pending == 0 or not poll_wait or (time.time() - start) >= poll_wait:
                    break
                time.sleep(poll_interval)
        else:
            while True:
                resolved, no_num, still = poll_reveals(apollo_client, store)
                log.info("poll: +%s resolved, +%s no_number, %s pending",
                         resolved, no_num, still)
                if still == 0 or not poll_wait or (time.time() - start) >= poll_wait:
                    break
                time.sleep(poll_interval)
        merged = merge_phones(all_contacts, store)
        log.info("Merged %s phone numbers.", merged)

    persist_now()

    # Persist the REAL Apollo credit tally — 0 when everything came from cache or
    # the LARA path (so the summary never shows a misleading estimate).
    credits = apollo_client.credits_used if apollo_client is not None else 0
    usage = apollo_client.usage if apollo_client is not None else {}
    try:
        atomic_write_json(out / "enrich_credits.json", {
            "apollo_credits": credits, "usage": usage,
            "cache_hits": cache_hits,
            "exhausted": bool(apollo_client is not None and apollo_client.exhausted),
            "updated": datetime.now().isoformat(),
        })
    except OSError:
        pass

    log.info("Done. %s contacts -> %s%s", len(all_contacts), contacts_path,
             f" ({cache_hits} companies from cache)" if cache_hits else "")
    return all_contacts
