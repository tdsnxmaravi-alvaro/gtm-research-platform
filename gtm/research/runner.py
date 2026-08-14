"""Research runner — orchestrate a campaign's research stage.

Provided mode: batch the supplied companies, build a qualify prompt per batch,
call the provider, parse + score results. Resumable (per-company state) with
per-batch audit logs.

Discover mode: build a broad or per-vertical prompt, call the provider, parse +
score the returned companies. Resumable per (product, vertical).

Manual provider: `send()` is unsupported; use ingest_manual() with pasted output.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from ..config.schema import CampaignConfig, Mode, ProviderType, LLMProvider
from ..prompts import build_prompt, format_companies
from ..ingest import parse_results, load_provided_list, write_rows_csv
from ..scoring import score_results
from ..providers import build_provider
from .cache import ResearchCache, _domain_or_name

OUT_COLS = [
    "product", "vertical", "company", "website", "country", "employees", "software_resold",
    "independence",
    "final_tier", "tier", "score",
    "tier_capped", "tier_cap_reason", "fit_summary", "recommended_products",
    "evidence_count", "has_verified_url", "evidence_urls", "notes", "passes",
    "ensemble_agreement", "ensemble_singleton", "evidence",
]

# Ensemble agreement-confidence (only applied when >1 provider runs research):
# a company independently surfaced by multiple providers is more trustworthy.
_AGREEMENT_BONUS = 5        # points per extra agreeing provider
_AGREEMENT_BONUS_CAP = 15   # max total boost
_SINGLETON_PENALTY = 5      # points off when only one provider found the company

# Retry a provider call on a transient error (timeout, 429, 5xx) before giving up,
# so one flaky batch doesn't silently drop an ensemble member.
_PROVIDER_RETRIES = 2       # extra attempts after the first (so up to 3 tries)
_RETRY_BACKOFF = 3          # seconds, multiplied by the attempt number

# Context columns carried from the provided list into the results (for the master).
_EMP_KEYS = ("number of employees", "employees", "company size", "size")
_SW_KEYS = ("other software in use", "software resold", "software", "other software")


def _ctx_val(row: dict, keys) -> str:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def _provider_for(config: CampaignConfig):
    for p in config.llm_providers:
        if p.name == config.research_provider:
            return build_provider(p)
    # default: a LARA research provider from standard env vars
    return build_provider(LLMProvider(name="lara-default", type=ProviderType.lara,
                                      web_search=True))


def _providers_for(config: CampaignConfig) -> list:
    """Return the research provider(s): an ensemble if research_providers is set,
    else the single research_provider."""
    names = config.research_providers
    if not names:
        return [_provider_for(config)]
    by_name = {p.name: p for p in config.llm_providers}
    return [build_provider(by_name[n]) for n in names if n in by_name]


def _read_existing_rows(path: Path) -> list[dict]:
    """Load previously written result rows so resumed runs accumulate."""
    if not path.exists():
        return []
    import csv
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _load_state(path: Path) -> set:
    if path.exists():
        try:
            return set(json.loads(path.read_text(encoding="utf-8")).get("done", []))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def _save_state(path: Path, done: set) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"done": sorted(done),
                                "updated": datetime.now().isoformat()},
                               indent=2, ensure_ascii=False), encoding="utf-8")


def _log(logs: Path, tag: str, prompt: str, response: str) -> None:
    logs.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in tag)[:50]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    (logs / f"{safe}_{ts}.md").write_text(
        f"# {tag}\n\n## PROMPT\n\n{prompt}\n\n## RESPONSE\n\n{response}\n",
        encoding="utf-8",
    )


def _aggregate_passes(parsed_lists: list[list[dict]], n_providers: int = 1) -> list[dict]:
    """Average scores across N passes per company to reduce run-to-run variance.

    Groups parsed rows by company, averages the (deterministic) score, unions the
    evidence URLs, and keeps the pass whose score is closest to the mean as the
    representative row (fit_summary/notes/recommended_products).

    In an ENSEMBLE (n_providers > 1), also applies agreement-confidence: a company
    independently surfaced by >=2 distinct providers gets a score bonus; one found
    by a single provider is flagged and lightly penalized. Adjusted rows clear the
    letter `tier` so it is re-derived from the adjusted score by score_results.
    """
    from statistics import mean

    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for rows in parsed_lists:
        for r in rows:
            key = (r.get("company") or "").strip().lower()
            if not key:
                continue
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(r)

    out: list[dict] = []
    for key in order:
        rs = groups[key]
        scores = [float(r["score"]) for r in rs
                  if str(r.get("score")).strip() not in ("", "None")]
        avg = round(mean(scores)) if scores else 0
        urls: list[str] = []
        for r in rs:
            for u in (r.get("evidence_urls") or "").split(";"):
                u = u.strip()
                if u and u not in urls:
                    urls.append(u)
        rep = min(rs, key=lambda r: abs(float(r.get("score") or 0) - avg))
        merged = dict(rep)
        merged["score"] = avg
        merged["evidence_urls"] = "; ".join(urls)
        merged["evidence_count"] = len(urls)
        merged["has_verified_url"] = bool(urls)
        merged["passes"] = len(rs)
        if n_providers > 1:
            found_by = {r.get("_provider") for r in rs if r.get("_provider")}
            agreement = len(found_by)
            merged["ensemble_agreement"] = agreement
            merged["ensemble_singleton"] = agreement < 2
            if agreement >= 2:
                bonus = min(_AGREEMENT_BONUS * (agreement - 1), _AGREEMENT_BONUS_CAP)
                merged["score"] = min(100, avg + bonus)
            else:
                merged["score"] = max(0, avg - _SINGLETON_PENALTY)
            merged["tier"] = ""  # re-derive from the confidence-adjusted score
        out.append(merged)
    return out


def _send_with_retry(prov, prompt: str, tag: str, pname: str, retries: int):
    """Call prov.send with retries + linear backoff on transient errors. Returns the
    ProviderResponse, or None after exhausting retries (so an ensemble member that
    flakes on one batch isn't silently dropped without trying again)."""
    for attempt in range(retries + 1):
        try:
            return prov.send(prompt)
        except Exception as exc:  # noqa: BLE001 - transient provider error
            if attempt >= retries:
                print(f"  !! provider error ({tag}/{pname}) after {attempt + 1} tries: {exc}")
                return None
            wait = _RETRY_BACKOFF * (attempt + 1)
            print(f"  .. provider {pname} error ({tag}); retry "
                  f"{attempt + 1}/{retries} in {wait}s: {exc}")
            time.sleep(wait)
    return None


def _run_batch(config, providers, prompt: str, logs: Path, tag: str,
               passes: int, delay: int) -> list[dict]:
    """Call each provider `passes` times, aggregate across the ensemble, and score.

    `providers` may be a single provider or a list (ensemble): scores are averaged
    across all provider x pass responses per company, and companies independently
    surfaced by >=2 providers get an agreement-confidence boost.
    """
    if not isinstance(providers, (list, tuple)):
        providers = [providers]
    retries = getattr(config, "research_retries", _PROVIDER_RETRIES)
    parsed_lists: list[list[dict]] = []
    for prov in providers:
        pname = getattr(prov, "name", "provider")
        for p in range(max(1, passes)):
            resp = _send_with_retry(prov, prompt, tag, pname, retries)
            if resp is None:
                continue
            multi = len(providers) > 1 or passes > 1
            _log(logs, f"{tag}_{pname}_pass{p+1}" if multi else tag, prompt, resp.text)
            rows = parse_results(resp.text)
            for r in rows:
                r["_provider"] = pname          # who surfaced this company (agreement)
            parsed_lists.append(rows)
            time.sleep(delay)
    if not parsed_lists:
        return []
    parsed = (_aggregate_passes(parsed_lists, n_providers=len(providers))
              if len(parsed_lists) > 1 else parsed_lists[0])
    for r in parsed:
        r.pop("_provider", None)
    return score_results(config, parsed)


def run_campaign(
    config: CampaignConfig,
    provider=None,
    *,
    batch_size: int = 3,
    limit: int = 0,
    delay: int = 2,
    resume: bool = True,
    passes: int = 1,
    out_dir: str | Path | None = None,
    progress_cb=None,
    should_cancel=None,
    use_research_cache: bool | None = None,
) -> list[dict]:
    out = Path(out_dir or (Path("campaigns") / config.name))
    logs = out / "logs"
    results_path = out / "results.csv"
    state_path = out / "state.json"
    if use_research_cache is None:
        use_research_cache = config.research_cache

    if provider is None:
        providers = _providers_for(config)
    else:
        providers = provider if isinstance(provider, (list, tuple)) else [provider]

    done = _load_state(state_path) if resume else set()
    # Resume must ACCUMULATE: load prior results so a limited/partial run appends
    # instead of overwriting results.csv with only the current batch.
    all_results: list[dict] = _read_existing_rows(results_path) if resume else []

    if config.mode == Mode.provided:
        rows = load_provided_list(config.provided_list_path,
                                  config.provided_column_overrides or None)
        pending = [r for r in rows if r.get("company") not in done]
        if limit:
            pending = pending[:limit]
        print(f"Provided: {len(rows)} companies | pending {len(pending)} | batch {batch_size}")

        cache = ResearchCache(path=out.parent / ".gtm_cache" / "research.json",
                              enabled=use_research_cache)
        total = len(pending) * max(1, len(config.products))
        processed = 0
        if progress_cb:
            progress_cb(0, total)
        for product in config.products:
            # Reuse a company's scored analysis for the same vendor/product/domain.
            to_research: list[dict] = []
            hits = 0
            for r in pending:
                ck = ResearchCache.key(config.vendor, config.target_type.value,
                                       product.name, _domain_or_name(r))
                cached = cache.get(ck)
                if cached is not None:
                    row = dict(cached)
                    row["company"] = r.get("company") or row.get("company", "")
                    row["product"] = product.name
                    row["vertical"] = ""
                    row["country"] = r.get("country") or config.country
                    row["employees"] = _ctx_val(r, _EMP_KEYS) or row.get("employees", "")
                    row["software_resold"] = _ctx_val(r, _SW_KEYS) or row.get("software_resold", "")
                    all_results.append(row)
                    done.add(r.get("company"))
                    hits += 1
                    processed += 1
                    if progress_cb:
                        progress_cb(processed, total)
                else:
                    to_research.append(r)
            if hits:
                _save_state(state_path, done)
                write_rows_csv(all_results, results_path, columns=OUT_COLS)
                print(f"  {product.name}: {hits} reused from research cache")

            def _process_batch(batch: list[dict], idx: int):
                prompt = build_prompt(config, product,
                                      company_input=format_companies(batch))
                tag = f"{product.name}_batch{idx + 1}"
                scored = _run_batch(config, providers, prompt, logs, tag, passes, delay)
                country_by = {(b.get("company") or "").strip().lower(): b.get("country", "")
                              for b in batch}
                domain_by = {(b.get("company") or "").strip().lower(): _domain_or_name(b)
                             for b in batch}
                emp_by = {(b.get("company") or "").strip().lower(): _ctx_val(b, _EMP_KEYS)
                          for b in batch}
                sw_by = {(b.get("company") or "").strip().lower(): _ctx_val(b, _SW_KEYS)
                         for b in batch}
                cache_items = []
                for r in scored:
                    comp = (r.get("company") or "").strip().lower()
                    r["product"] = product.name
                    r["vertical"] = ""
                    r["country"] = country_by.get(comp, config.country)
                    r["employees"] = emp_by.get(comp) or r.get("employees", "")
                    r["software_resold"] = sw_by.get(comp) or r.get("software_resold", "")
                    cache_items.append((ResearchCache.key(
                        config.vendor, config.target_type.value, product.name,
                        domain_by.get(comp, comp)), r))
                return batch, scored, cache_items

            def _accept(batch, scored, cache_items) -> None:
                for ck, r in cache_items:
                    cache.put(ck, r)
                all_results.extend(scored)
                # Only mark companies done when the batch produced results, so a
                # transient provider error (e.g. HTTP 499) is retried on resume.
                if scored:
                    for r in batch:
                        done.add(r.get("company"))
                    _save_state(state_path, done)
                    write_rows_csv(all_results, results_path, columns=OUT_COLS)

            batches = [to_research[i:i + batch_size]
                       for i in range(0, len(to_research), batch_size)]
            concurrency = max(1, getattr(config, "research_concurrency", 1) or 1)

            if concurrency <= 1 or len(batches) <= 1:
                for idx, batch in enumerate(batches):
                    if should_cancel and should_cancel():
                        print("  canceled — stopping after saved progress")
                        return all_results
                    _accept(*_process_batch(batch, idx))
                    processed += len(batch)
                    if progress_cb:
                        progress_cb(min(processed, total), total)
                    print(f"  batch {idx + 1}: results saved")
                    time.sleep(delay)
            else:
                # Run batches in concurrent waves — parallel LLM requests so a large
                # list finishes far faster. State is saved after each completed batch.
                from concurrent.futures import ThreadPoolExecutor, as_completed
                w = 0
                while w < len(batches):
                    if should_cancel and should_cancel():
                        print("  canceled — stopping after saved progress")
                        return all_results
                    wave = list(enumerate(batches))[w:w + concurrency]
                    with ThreadPoolExecutor(max_workers=concurrency) as ex:
                        futs = [ex.submit(_process_batch, b, idx) for idx, b in wave]
                        for fut in as_completed(futs):
                            batch, scored, cache_items = fut.result()
                            _accept(batch, scored, cache_items)
                            processed += len(batch)
                            if progress_cb:
                                progress_cb(min(processed, total), total)
                            print(f"  batch: +{len(scored)} results")
                    w += concurrency

    else:  # discover
        targets = config.verticals or [None]
        run_countries = config.countries or [config.country]
        total = len(config.products) * len(targets) * len(run_countries)
        step_n = 0
        if progress_cb:
            progress_cb(0, total)
        for country in run_countries:
            for product in config.products:
                for vert in targets:
                    if should_cancel and should_cancel():
                        print("  canceled — stopping after saved progress")
                        return all_results
                    key = f"{country}|{product.name}|{vert.slug if vert else 'broad'}"
                    if key in done:
                        step_n += 1
                        if progress_cb:
                            progress_cb(step_n, total)
                        continue
                    prompt = build_prompt(config, product, vertical=vert, country=country)
                    scored = _run_batch(config, providers, prompt, logs,
                                        key.replace("|", "_").replace(" ", ""), passes, delay)
                    for r in scored:
                        r["product"] = product.name
                        r["vertical"] = vert.name if vert else ""
                        r["country"] = country
                    all_results.extend(scored)
                    done.add(key)
                    _save_state(state_path, done)
                    write_rows_csv(all_results, results_path, columns=OUT_COLS)
                    step_n += 1
                    if progress_cb:
                        progress_cb(step_n, total)
                    print(f"  {key}: +{len(scored)} results")
                    time.sleep(delay)

    print(f"Done. {len(all_results)} results -> {results_path}")
    return all_results


def ingest_manual(config: CampaignConfig, raw_texts: list[str],
                  out_dir: str | Path | None = None) -> list[dict]:
    """Parse + score pasted LLM outputs (manual research path)."""
    out = Path(out_dir or (Path("campaigns") / config.name))
    results: list[dict] = []
    for text in raw_texts:
        results.extend(score_results(config, parse_results(text)))
    write_rows_csv(results, out / "results.csv", columns=OUT_COLS)
    return results
