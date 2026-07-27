"""Command-line interface for the GTM Research Platform.

    python -m gtm validate  campaigns/spain-bricscad.yaml
    python -m gtm prompt    campaigns/spain-bricscad.yaml --company "Acme CAD"
    python -m gtm estimate  campaigns/spain-bricscad.yaml
    python -m gtm run       campaigns/spain-bricscad.yaml --batch-size 3 --limit 6
    python -m gtm enrich    campaigns/spain-bricscad.yaml --limit 6
    python -m gtm ingest-manual campaigns/spain-bricscad.yaml out1.md out2.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_campaign
from .prompts import build_prompt, format_companies
from .ingest import load_provided_list
from .research import run_campaign, ingest_manual
from .enrichment import run_enrichment


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
                 delay=args.delay, resume=not args.no_resume)


def cmd_enrich(args):
    c = load_campaign(args.config)
    run_enrichment(c, limit=args.limit, delay=args.delay,
                   resume=not args.no_resume,
                   poll_wait=args.poll_wait, poll_interval=args.poll_interval)


def cmd_ingest_manual(args):
    c = load_campaign(args.config)
    texts = [Path(f).read_text(encoding="utf-8") for f in args.files]
    res = ingest_manual(c, texts)
    print(f"parsed {len(res)} results -> campaigns/{c.name}/results.csv")


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
    en.set_defaults(func=cmd_enrich)

    im = sub.add_parser("ingest-manual", help="Parse pasted LLM outputs")
    im.add_argument("config")
    im.add_argument("files", nargs="+")
    im.set_defaults(func=cmd_ingest_manual)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
