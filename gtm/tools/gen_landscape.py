"""Research-driven generator for vertical vendor-landscape brands (issue #18).

Instead of hand-picking the ``example_reseller_software`` for each vertical, this
runs the platform's own research provider (web search) to propose, per vendor x
vertical, the REAL software brands whose independent resellers operate in that
vertical — the recruit channel — excluding the vendor's own products and
competitor-locked-only brands. Output is a reviewable JSON artifact (brands +
source URLs); a human folds the approved brands into ``vertical_presets.py``.

Usage (LARA research provider, env-configured):
    python -m gtm.tools.gen_landscape --vendor Trimble
    python -m gtm.tools.gen_landscape --vendor Bricsys --slugs cad-app-developers
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from ..config.schema import LLMProvider, ProviderType
from ..providers.base import BaseProvider
from ..providers.factory import build_provider
from ..prompts.vertical_presets import (
    VENDOR_OWN_PRODUCTS, VENDOR_VERTICALS, VERTICAL_PRESETS,
    exclusion_note, verticals_for, TIERS,
)

# Overlay file consumed by vertical_presets._load_research_overlay().
OVERLAY_PATH = Path(__file__).resolve().parents[1] / "prompts" / "landscape_brands.json"

LANDSCAPE_PROMPT = """You are a channel-research analyst for TD SYNNEX.

TARGET VENDOR: {vendor} — we want to recruit NEW independent resellers who could ADD
{vendor} to their portfolio.
RESELLER VERTICAL: "{name}"
What this vertical is: {focus}

TASK: Using web search, list the 5-7 REAL, currently-marketed software brands/products
whose INDEPENDENT resellers / VARs operate in this vertical and would be the best recruit
targets for {vendor}. These are brands such resellers ALREADY sell (the recruit channel) —
NOT {vendor}'s own products, and NOT raw file formats.

STRICT RULES:
- Every brand must be a real, verifiable product; cite a working source URL for each.
- EXCLUDE {vendor}'s own products / brands it owns: {own}.
- EXCLUDE brands sold only through competitor-locked exclusive channels: {excl}
- Prefer brands with an independent reseller / VAR channel (not direct-only).

Return STRICT JSON only (no prose, no markdown fences):
{{"software": [
  {{"brand": "Product name", "maker": "vendor company",
    "reseller_channel": "how independent resellers sell it",
    "source_url": "https://..."}}
]}}"""

NEUTRAL_PROMPT = """You are a channel-research analyst for TD SYNNEX.

RESELLER VERTICAL: "{name}"
What this vertical is: {focus}

TASK: Using web search, list the 5-7 REAL, currently-marketed software brands/products
whose INDEPENDENT resellers / VARs operate in this vertical — brands such resellers ALREADY
sell (the recruit channel). NOT raw file formats.

STRICT RULES:
- Every brand must be a real, verifiable product; cite a working source URL for each.
- EXCLUDE these products (our own vendors' portfolio): {own}.
- Prefer brands with an independent reseller / VAR channel (not direct-only).

Return STRICT JSON only (no prose, no markdown fences):
{{"software": [
  {{"brand": "Product name", "maker": "vendor company",
    "reseller_channel": "how independent resellers sell it",
    "source_url": "https://..."}}
]}}"""


def _vendors_using(slug: str) -> list[str]:
    return [v for v, items in VENDOR_VERTICALS.items() if any(s == slug for s, _ in items)]


def _own_products_for_slug(slug: str) -> list[str]:
    """Union of the own-products of every vendor that uses this (shared) vertical."""
    tokens: set[str] = set()
    for v in _vendors_using(slug):
        tokens.update(VENDOR_OWN_PRODUCTS.get(v, []))
    return sorted(tokens)


def build_landscape_prompt(vendor: str, vertical: dict) -> str:
    own = ", ".join(VENDOR_OWN_PRODUCTS.get(vendor, [])) or "(none)"
    excl = exclusion_note(vendor) or "(none)"
    return LANDSCAPE_PROMPT.format(
        vendor=vendor, name=vertical["name"], focus=vertical["focus"],
        own=own, excl=excl,
    )


def build_neutral_prompt(slug: str, vertical: dict) -> str:
    own = ", ".join(_own_products_for_slug(slug)) or "(none)"
    return NEUTRAL_PROMPT.format(name=vertical["name"], focus=vertical["focus"], own=own)



def _parse_json(text: str) -> dict | None:
    """Extract the first JSON object from a response (tolerant of fences/prose)."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    blob = fenced.group(1) if fenced else text
    start = blob.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(blob)):
        if blob[i] == "{":
            depth += 1
        elif blob[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(blob[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _lara_provider() -> BaseProvider:
    cfg = LLMProvider(name="lara", type=ProviderType.lara, web_search=True)
    return build_provider(cfg)


def generate(vendor: str, provider: BaseProvider, slugs: list[str] | None = None,
             delay: float = 2.0, progress=print) -> list[dict]:
    """Research the landscape for a vendor's verticals. Returns proposals per slug."""
    verts = verticals_for(vendor, tiers=TIERS)
    if slugs:
        keep = set(slugs)
        verts = [v for v in verts if v["slug"] in keep]
    out: list[dict] = []
    for v in verts:
        prompt = build_landscape_prompt(vendor, v)
        resp = provider.send(prompt, web_search=True)
        parsed = _parse_json(resp.text) or {}
        software = parsed.get("software", []) if isinstance(parsed, dict) else []
        out.append({
            "slug": v["slug"],
            "name": v["name"],
            "current": v["example_reseller_software"],
            "proposed": [s.get("brand", "") for s in software if s.get("brand")],
            "detail": software,
            "sources": resp.sources,
        })
        progress(f"  {vendor}/{v['slug']}: {len(software)} brands")
        time.sleep(delay)
    return out


def generate_all(provider: BaseProvider, slugs: list[str] | None = None,
                 delay: float = 2.0, progress=print) -> list[dict]:
    """Research every UNIQUE vertical once, vendor-neutral, excluding the union of
    the owning vendors' own products."""
    items = [(slug, v) for slug, v in VERTICAL_PRESETS.items()
             if not slugs or slug in set(slugs)]
    out: list[dict] = []
    for slug, v in items:
        prompt = build_neutral_prompt(slug, v)
        resp = provider.send(prompt, web_search=True)
        parsed = _parse_json(resp.text) or {}
        software = parsed.get("software", []) if isinstance(parsed, dict) else []
        out.append({
            "slug": slug,
            "name": v["name"],
            "current": v["example_reseller_software"],
            "proposed": [s.get("brand", "") for s in software if s.get("brand")],
            "detail": software,
            "sources": resp.sources,
        })
        progress(f"  {slug}: {len(software)} brands")
        time.sleep(delay)
    return out


def _self_ref_safe(slug: str, brands: list[str]) -> list[str]:
    """Drop any brand that contains an own-product token of a vendor using this slug."""
    tokens = [t.lower() for t in _own_products_for_slug(slug)]
    out = []
    for b in brands:
        low = b.lower()
        if not any(t in low for t in tokens):
            out.append(b)
    return out


def write_overlay(results: list[dict], top: int = 5, path: Path = OVERLAY_PATH) -> dict:
    """Merge researched brands into the landscape_brands.json overlay (self-ref-safe)."""
    overlay: dict = {}
    if path.exists():
        try:
            overlay = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            overlay = {}
    for r in results:
        brands = _self_ref_safe(r["slug"], r["proposed"])[:top]
        if brands:
            overlay[r["slug"]] = brands
    path.write_text(json.dumps(overlay, indent=2, ensure_ascii=False), encoding="utf-8")
    return overlay


def main() -> None:
    ap = argparse.ArgumentParser(description="Research vendor-landscape brands per vertical.")
    ap.add_argument("--vendor", help="research one vendor's verticals")
    ap.add_argument("--all", action="store_true", help="research every unique vertical once")
    ap.add_argument("--slugs", nargs="*", help="limit to these vertical slugs")
    ap.add_argument("--apply", action="store_true",
                    help="merge results into gtm/prompts/landscape_brands.json")
    ap.add_argument("--top", type=int, default=5, help="brands per vertical when applying")
    ap.add_argument("--out", default=None, help="raw output JSON path")
    ap.add_argument("--delay", type=float, default=2.0)
    args = ap.parse_args()

    provider = _lara_provider()
    if args.all:
        print(f"Researching the FULL catalogue via {provider.name}…")
        results = generate_all(provider, slugs=args.slugs, delay=args.delay)
        default_out = Path("campaigns") / "_landscape" / "all.json"
    elif args.vendor:
        print(f"Researching {args.vendor} landscape via {provider.name}…")
        results = generate(args.vendor, provider, slugs=args.slugs, delay=args.delay)
        default_out = Path("campaigns") / "_landscape" / f"{args.vendor}.json"
    else:
        ap.error("pass --all or --vendor")

    out = Path(args.out or default_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(results)} verticals -> {out}")

    if args.apply:
        write_overlay(results, top=args.top)
        print(f"Applied top-{args.top} brands -> {OVERLAY_PATH}")


if __name__ == "__main__":
    main()
