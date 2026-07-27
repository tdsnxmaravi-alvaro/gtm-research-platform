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
    out_dir: str | Path | None = None,
) -> list[EnrichedContact]:
    """Enrich qualified companies. Returns the enriched contacts."""
    enr = config.enrichment
    if enr.want == EnrichWant.none:
        print("Enrichment want=none — nothing to do.")
        return []

    out = Path(out_dir or (Path("campaigns") / config.name))
    if rows is None:
        rows = _load_rows(out / "results.csv")
    if not rows:
        print("No qualified rows to enrich (run research first).")
        return []

    contacts_path = out / "contacts.csv"
    state_path = out / "enrich_state.json"
    done = _load_done(state_path) if resume else set()

    pending = [r for r in rows if (r.get("company") or "").strip()
               and r.get("company") not in done]
    if limit:
        pending = pending[:limit]
    print(f"Enrich: {len(rows)} companies | pending {len(pending)} | "
          f"provider={enr.provider.value} | want={enr.want.value}")

    all_contacts: list[EnrichedContact] = []

    # Build the provider once.
    apollo_client = None
    lara_provider = None
    if enr.provider == EnrichProvider.apollo:
        locations = enr.locations or apollo_locations_for(config.country)
        apollo_client = ApolloClient(seniorities=enr.seniorities, locations=locations)
    else:
        lara_provider = build_lara_enrichment_provider()

    for r in pending:
        company = r.get("company")
        try:
            if apollo_client is not None:
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

    print(f"Done. {len(all_contacts)} contacts -> {contacts_path}")
    return all_contacts
