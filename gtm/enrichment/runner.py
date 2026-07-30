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

import csv
import json
import time
from datetime import datetime
from pathlib import Path

from ..config.schema import (
    CampaignConfig, EnrichProvider, EnrichWant, apollo_locations_for,
)
from ..ingest import write_rows_csv
from .models import EnrichedContact, CONTACT_COLS
from .apollo import (
    ApolloClient, enrich_company,
    PhoneRevealStore, fire_reveals, poll_reveals, merge_phones,
)
from .lara_agent import build_lara_enrichment_provider, enrich_company_lara


def _load_rows(results_path: Path) -> list[dict]:
    if not results_path.exists():
        return []
    with open(results_path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _load_done(path: Path) -> set:
    if path.exists():
        try:
            return set(json.loads(path.read_text(encoding="utf-8")).get("done", []))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def _save_done(path: Path, done: set) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"done": sorted(done),
                                "updated": datetime.now().isoformat()},
                               indent=2, ensure_ascii=False), encoding="utf-8")


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
        print("Enrichment want=none — nothing to do.")
        return []

    out = Path(out_dir or (Path("campaigns") / config.name))
    if rows is None:
        # Prefer the consolidated shortlist (deduped + tier-filtered) so we only
        # enrich companies worth contacting; fall back to raw results.
        rows = _load_rows(out / "master.csv") or _load_rows(out / "results.csv")
    if not rows:
        print("No qualified rows to enrich (run research + consolidate first).")
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

    pending = [r for r in rows if (r.get("company") or "").strip()
               and r.get("company") not in done
               and _TIER_ORDER.get(_row_tier(r), 9) <= cap]
    if limit:
        pending = pending[:limit]
    print(f"Enrich: {len(rows)} companies | tier>={(min_tier or config.outreach.min_tier)} "
          f"| pending {len(pending)} | provider={enr.provider.value} | want={enr.want.value}")

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

    for _i, r in enumerate(pending, 1):
        if should_cancel and should_cancel():
            print("  canceled — stopping enrichment (state saved)")
            break
        if progress_cb:
            progress_cb(_i, len(pending))
        company = r.get("company")
        domain = extract_domain(r.get("website") or "")
        cached = cache.get(domain) if domain else None
        if cached is not None:
            all_contacts.extend(cached)
            done.add(company)
            _save_done(state_path, done)
            write_rows_csv([c.to_row() for c in all_contacts], contacts_path,
                           columns=CONTACT_COLS)
            cache_hits += 1
            print(f"  {company}: {len(cached)} contacts (cache)")
            continue
        try:
            _ensure_provider()
            if enr.provider == EnrichProvider.apollo:
                got = enrich_company(apollo_client, r,
                                     max_contacts=enr.max_contacts, delay=delay)
            else:
                got = enrich_company_lara(lara_provider, r, country=config.country,
                                          max_contacts=enr.max_contacts,
                                          language=config.language or "en")
        except Exception as exc:  # noqa: BLE001 - log & continue
            print(f"  !! enrich error for {company}: {exc}")
            continue
        all_contacts.extend(got)
        if domain:
            cache.put(domain, got)
        done.add(company)
        _save_done(state_path, done)
        write_rows_csv([c.to_row() for c in all_contacts], contacts_path,
                       columns=CONTACT_COLS)
        print(f"  {company}: +{len(got)} contacts")

    # Phone reveals (Apollo only, when requested).
    if (apollo_client is not None and enr.want == EnrichWant.emails_phones
            and all_contacts):
        store = PhoneRevealStore(out / "phone_reveals.json")
        fired = fire_reveals(apollo_client, all_contacts, store)
        print(f"Phone reveals fired: {fired} (numbers arrive async ~40 min).")
        start = time.time()
        if use_webhook:
            # A separate `gtm webhook` process owns store writes; we only read
            # here to avoid a cross-process read-modify-write race.
            print("Waiting for webhook callbacks (run `gtm webhook` + cloudflared).")
            while True:
                store.reload()
                pending = store.pending_count()
                done = len(store.data) - pending
                print(f"  monitor: {done} resolved, {pending} pending")
                if pending == 0 or not poll_wait or (time.time() - start) >= poll_wait:
                    break
                time.sleep(poll_interval)
        else:
            while True:
                resolved, no_num, still = poll_reveals(apollo_client, store)
                print(f"  poll: +{resolved} resolved, +{no_num} no_number, {still} pending")
                if still == 0 or not poll_wait or (time.time() - start) >= poll_wait:
                    break
                time.sleep(poll_interval)
        merged = merge_phones(all_contacts, store)
        print(f"Merged {merged} phone numbers.")
        write_rows_csv([c.to_row() for c in all_contacts], contacts_path,
                       columns=CONTACT_COLS)

    # Persist the REAL Apollo credit tally — 0 when everything came from cache or
    # the LARA path (so the summary never shows a misleading estimate).
    credits = apollo_client.credits_used if apollo_client is not None else 0
    usage = apollo_client.usage if apollo_client is not None else {}
    try:
        (out / "enrich_credits.json").write_text(
            json.dumps({"apollo_credits": credits, "usage": usage,
                        "cache_hits": cache_hits,
                        "updated": datetime.now().isoformat()},
                       ensure_ascii=False, indent=2),
            encoding="utf-8")
    except OSError:
        pass

    print(f"Done. {len(all_contacts)} contacts -> {contacts_path}"
          + (f" ({cache_hits} companies from cache)" if cache_hits else ""))
    return all_contacts
