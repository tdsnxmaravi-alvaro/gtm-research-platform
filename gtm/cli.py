"""Command-line interface for the GTM Research Platform.

    python -m gtm validate  campaigns/spain-bricscad.yaml
    python -m gtm prompt    campaigns/spain-bricscad.yaml --company "Acme CAD"
    python -m gtm estimate  campaigns/spain-bricscad.yaml
    python -m gtm run       campaigns/spain-bricscad.yaml --batch-size 3 --limit 6
    python -m gtm enrich    campaigns/spain-bricscad.yaml --limit 6
    python -m gtm webhook   campaigns/spain-bricscad.yaml            # phone-reveal receiver
    python -m gtm ingest-manual campaigns/spain-bricscad.yaml out1.md out2.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_campaign
from .prompts import build_prompt, format_companies
from .ingest import load_provided_list, inspect_provided_list
from .research import run_campaign, ingest_manual
from .enrichment import run_enrichment, run_webhook_server
from .consolidate import build_master
from .outreach import run_outreach


def _provided_count(cfg) -> int:
    if cfg.provided_list_path and Path(cfg.provided_list_path).exists():
        return len(load_provided_list(cfg.provided_list_path))
    return 0


def cmd_validate(args):
    c = load_campaign(args.config)
    print(f"OK  {c.name}")
    print(f"  target={c.target_type.value}  mode={c.mode.value}  country={c.country}  lang={c.language}")
    print(f"  template={c.prompt_template_key()}  products={[p.name for p in c.products]}")
    if c.mode.value == "provided":
        n = _provided_count(c)
        print(f"  provided list: {n} companies"
              + (f"  (est. Apollo credits: {c.enrichment.estimate_credits(n)})" if n else ""))


def cmd_prompt(args):
    c = load_campaign(args.config)
    company_input = None
    if c.mode.value == "provided":
        company_input = format_companies([{"company": args.company or "Example Co.", "website": ""}])
    vert = c.verticals[0] if c.verticals else None
    print(build_prompt(c, c.products[0], company_input=company_input, vertical=vert))


def cmd_estimate(args):
    c = load_campaign(args.config)
    n = args.companies or _provided_count(c)
    print(f"companies={n}  want={c.enrichment.want.value}  max_contacts={c.enrichment.max_contacts}")
    print(f"estimated Apollo credits: {c.enrichment.estimate_credits(n)}")


def cmd_run(args):
    c = load_campaign(args.config)
    run_campaign(c, batch_size=args.batch_size, limit=args.limit,
                 delay=args.delay, resume=not args.no_resume, passes=args.passes)


def cmd_enrich(args):
    c = load_campaign(args.config)
    if args.want:
        from .config.schema import EnrichWant
        c.enrichment.want = EnrichWant(args.want)
    if args.provider:
        from .config.schema import EnrichProvider
        c.enrichment.provider = EnrichProvider(args.provider)
    run_enrichment(c, limit=args.limit, delay=args.delay,
                   resume=not args.no_resume,
                   poll_wait=args.poll_wait, poll_interval=args.poll_interval,
                   use_webhook=args.webhook, use_cache=not args.no_cache,
                   max_reveals=args.max_reveals)


def cmd_webhook(args):
    c = load_campaign(args.config)
    store_path = Path("campaigns") / c.name / "phone_reveals.json"
    run_webhook_server(store_path, port=args.port, path=args.path, tunnel=args.tunnel)


def cmd_apollo_profile(args):
    """Check the Apollo key + credit balance without spending (uses api_profile)."""
    from .enrichment.apollo import ApolloClient
    ok, msg = ApolloClient().preflight()
    print(("OK — " if ok else "BLOCKED — ") + msg)
    raise SystemExit(0 if ok else 1)


def cmd_consolidate(args):
    c = load_campaign(args.config)
    build_master(c, min_tier=args.min_tier)


def cmd_outreach(args):
    c = load_campaign(args.config)
    run_outreach(c, min_tier=args.min_tier, limit=args.limit, use_agent=args.agent)


def cmd_ingest_manual(args):
    c = load_campaign(args.config)
    texts = [Path(f).read_text(encoding="utf-8") for f in args.files]
    res = ingest_manual(c, texts)
    print(f"parsed {len(res)} results -> campaigns/{c.name}/results.csv")


def cmd_inspect(args):
    """Pre-flight a provided list (or a campaign's list): columns + data quality."""
    target = args.target
    if target.lower().endswith((".yaml", ".yml")):
        c = load_campaign(target)
        path = c.provided_list_path
        if not path:
            print(f"Campaign '{c.name}' has no provided_list_path.")
            return
    else:
        path = target

    rep = inspect_provided_list(path, use_ai=args.ai)
    print(f"File   : {rep['path']}  ({rep['format']})")
    print(f"Headers: {rep['raw_headers']}")
    print("Mapping (detected):")
    for h, m in rep["mapping"].items():
        tag = "  <-- company" if m == "company" else ("  <-- website" if m == "website" else "")
        print(f"  {h!r} -> {m}{tag}")
    if rep.get("ai_mapping"):
        print(f"AI mapping: {rep['ai_mapping']}")
    elif args.ai:
        from .ingest import ai_available
        if ai_available():
            print("AI mapping: no usable response this run — using rules-based mapping.")
        else:
            print("AI mapping: schema-mapper agent not configured (set LARA_SCHEMA_ASSISTANT_ID).")
    print(f"Rows   : {rep['raw_rows']} total | {rep['with_company']} with company | "
          f"{rep['with_website']} with website | {rep['missing_website']} missing website")
    if rep["duplicates"]:
        print(f"Dupes  : {rep['duplicates']} duplicate company name(s)")
    if rep["context_fields_present"]:
        print(f"Context: {rep['context_fields_present']}")
    if rep["warnings"]:
        print("Warnings:")
        for w in rep["warnings"]:
            print(f"  ! {w}")
    print("Minimum (name + website): " +
          ("OK" if rep["has_company_col"] and rep["has_website_col"]
           else "INCOMPLETE — ask the stakeholder for at least name + website"))
    print("Ready to run: " + ("YES" if rep["ok"] else "NO"))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gtm", description="GTM Research Platform CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="Load + validate a campaign config")
    v.add_argument("config")
    v.set_defaults(func=cmd_validate)

    pr = sub.add_parser("prompt", help="Preview the research prompt")
    pr.add_argument("config")
    pr.add_argument("--company", default="")
    pr.set_defaults(func=cmd_prompt)

    e = sub.add_parser("estimate", help="Estimate Apollo enrichment credits")
    e.add_argument("config")
    e.add_argument("--companies", type=int, default=0)
    e.set_defaults(func=cmd_estimate)

    r = sub.add_parser("run", help="Run the research stage")
    r.add_argument("config")
    r.add_argument("--batch-size", type=int, default=3)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--delay", type=int, default=2)
    r.add_argument("--passes", type=int, default=1,
                   help="Average N research passes per batch to reduce variance (score var drops ~1/sqrt(N))")
    r.add_argument("--no-resume", action="store_true")
    r.set_defaults(func=cmd_run)

    en = sub.add_parser("enrich", help="Resolve contacts for qualified companies")
    en.add_argument("config")
    en.add_argument("--limit", type=int, default=0)
    en.add_argument("--delay", type=float, default=0.5)
    en.add_argument("--no-resume", action="store_true")
    en.add_argument("--poll-wait", type=int, default=0,
                    help="Max seconds to keep polling Apollo phone reveals")
    en.add_argument("--poll-interval", type=int, default=600)
    en.add_argument("--want", choices=["none", "emails", "emails+phones"],
                    help="Override enrichment.want for this run")
    en.add_argument("--provider", choices=["apollo", "lara"],
                    help="Override enrichment.provider for this run")
    en.add_argument("--no-cache", action="store_true",
                    help="Ignore the shared contact cache (force fresh enrichment)")
    en.add_argument("--webhook", action="store_true",
                    help="Use a live webhook (run `gtm webhook` + cloudflared) "
                         "instead of polling for phone reveals")
    en.add_argument("--max-reveals", type=int, default=None,
                    help="Cap how many phone reveals to fire (bounds Apollo spend)")
    en.set_defaults(func=cmd_enrich)

    wh = sub.add_parser("webhook", help="Run the Apollo phone-reveal webhook receiver")
    wh.add_argument("config")
    wh.add_argument("--port", type=int, default=8000)
    wh.add_argument("--path", default="/apollo-webhook")
    wh.add_argument("--tunnel", action="store_true",
                    help="Auto-open a cloudflared tunnel + set APOLLO_WEBHOOK_URL "
                         "(one command, no manual .env editing)")
    wh.set_defaults(func=cmd_webhook)

    ap = sub.add_parser("apollo-profile",
                        help="Check the Apollo key + credit balance (no spend)")
    ap.set_defaults(func=cmd_apollo_profile)

    ins = sub.add_parser("inspect", help="Pre-flight a provided list (columns + data quality)")
    ins.add_argument("target", help="A list file (.csv/.xlsx) or a campaign .yaml")
    ins.add_argument("--no-ai", dest="ai", action="store_false", default=True,
                     help="Disable the LARA schema-mapper; use rules-based mapping only")
    ins.set_defaults(func=cmd_inspect)

    co = sub.add_parser("consolidate", help="Build the master list (results + contacts)")
    co.add_argument("config")
    co.add_argument("--min-tier", default=None, help="Only include tiers >= this (e.g. B)")
    co.set_defaults(func=cmd_consolidate)

    ou = sub.add_parser("outreach", help="Generate .eml drafts from the master list")
    ou.add_argument("config")
    ou.add_argument("--min-tier", default=None, help="Only draft for tiers >= this")
    ou.add_argument("--limit", type=int, default=0)
    ou.add_argument("--no-agent", dest="agent", action="store_false", default=True,
                    help="Use the deterministic template instead of the LARA outreach agent")
    ou.set_defaults(func=cmd_outreach)

    im = sub.add_parser("ingest-manual", help="Parse pasted LLM outputs")
    im.add_argument("config")
    im.add_argument("files", nargs="+")
    im.set_defaults(func=cmd_ingest_manual)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    _load_env()
    args.func(args)


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


if __name__ == "__main__":
    main()
