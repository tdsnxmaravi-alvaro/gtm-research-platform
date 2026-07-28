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

OUT_COLS = [
    "product", "vertical", "company", "website", "final_tier", "tier", "score",
    "tier_capped", "tier_cap_reason", "fit_summary", "recommended_products",
    "evidence_count", "has_verified_url", "evidence_urls", "notes", "passes", "evidence",
]


def _provider_for(config: CampaignConfig):
    for p in config.llm_providers:
        if p.name == config.research_provider:
            return build_provider(p)
    # default: a LARA research provider from standard env vars
    return build_provider(LLMProvider(name="lara-default", type=ProviderType.lara,
                                      web_search=True))


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


def _aggregate_passes(parsed_lists: list[list[dict]]) -> list[dict]:
    """Average scores across N passes per company to reduce run-to-run variance.

    Groups parsed rows by company, averages the (deterministic) score, unions the
    evidence URLs, and keeps the pass whose score is closest to the mean as the
    representative row (fit_summary/notes/recommended_products).
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
        out.append(merged)
    return out


def _run_batch(config, provider, prompt: str, logs: Path, tag: str,
               passes: int, delay: int) -> list[dict]:
    """Call the provider `passes` times, aggregate, and score the batch."""
    parsed_lists: list[list[dict]] = []
    for p in range(max(1, passes)):
        try:
            resp = provider.send(prompt)
        except Exception as exc:  # noqa: BLE001 - log and continue
            print(f"  !! provider error ({tag}) pass {p+1}: {exc}")
            continue
        _log(logs, f"{tag}_pass{p+1}" if passes > 1 else tag, prompt, resp.text)
        parsed_lists.append(parse_results(resp.text))
        if p < passes - 1:
            time.sleep(delay)
    if not parsed_lists:
        return []
    parsed = _aggregate_passes(parsed_lists) if len(parsed_lists) > 1 else parsed_lists[0]
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
) -> list[dict]:
    out = Path(out_dir or (Path("campaigns") / config.name))
    logs = out / "logs"
    results_path = out / "results.csv"
    state_path = out / "state.json"

    if provider is None:
        provider = _provider_for(config)

    done = _load_state(state_path) if resume else set()
    all_results: list[dict] = []

    if config.mode == Mode.provided:
        rows = load_provided_list(config.provided_list_path)
        pending = [r for r in rows if r.get("company") not in done]
        if limit:
            pending = pending[:limit]
        print(f"Provided: {len(rows)} companies | pending {len(pending)} | batch {batch_size}")

        for product in config.products:
            for i in range(0, len(pending), batch_size):
                batch = pending[i:i + batch_size]
                prompt = build_prompt(config, product,
                                      company_input=format_companies(batch))
                tag = f"{product.name}_batch{i//batch_size+1}"
                scored = _run_batch(config, provider, prompt, logs, tag, passes, delay)
                for r in scored:
                    r["product"] = product.name
                    r["vertical"] = ""
                all_results.extend(scored)
                # Only mark companies done when the batch produced results, so a
                # transient provider error (e.g. HTTP 499) is retried on resume.
                if scored:
                    for r in batch:
                        done.add(r.get("company"))
                    _save_state(state_path, done)
                    write_rows_csv(all_results, results_path, columns=OUT_COLS)
                print(f"  batch {i//batch_size+1}: +{len(scored)} results")
                time.sleep(delay)

    else:  # discover
        targets = config.verticals or [None]
        for product in config.products:
            for vert in targets:
                key = f"{product.name}|{vert.slug if vert else 'broad'}"
                if key in done:
                    continue
                prompt = build_prompt(config, product, vertical=vert)
                scored = _run_batch(config, provider, prompt, logs,
                                    key.replace("|", "_"), passes, delay)
                for r in scored:
                    r["product"] = product.name
                    r["vertical"] = vert.name if vert else ""
                all_results.extend(scored)
                done.add(key)
                _save_state(state_path, done)
                write_rows_csv(all_results, results_path, columns=OUT_COLS)
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
