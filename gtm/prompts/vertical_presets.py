"""Vendor-native reseller verticals for DISCOVER mode.

Catalogue and per-vendor maps live in ``gtm/prompts/data/*.yaml`` so onboarding
a vendor is a data change. ``landscape_brands.json`` still overlays researched
brands onto ``example_reseller_software``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

# Tier constants (ordered best-first).
CORE = "core"
SECONDARY = "secondary"
DEFER = "defer"
TIERS = (CORE, SECONDARY, DEFER)

_DATA = Path(__file__).parent / "data"


def _load_yaml(name: str):
    return yaml.safe_load((_DATA / name).read_text(encoding="utf-8")) or {}


VERTICAL_PRESETS: dict[str, dict] = _load_yaml("verticals.yaml")
VENDOR_VERTICALS: dict[str, list[tuple[str, str]]] = {
    vendor: [(slug, tier) for slug, tier in items]
    for vendor, items in _load_yaml("vendor_verticals.yaml").items()
}
VENDOR_EXCLUSIONS: dict[str, dict[str, list[str]]] = _load_yaml("vendor_exclusions.yaml")
VENDOR_OWN_PRODUCTS: dict[str, list[str]] = _load_yaml("vendor_own_products.yaml")


def vertical_preset(slug: str) -> dict:
    """Return the catalogue entry for a slug (raises KeyError if unknown)."""
    return VERTICAL_PRESETS[slug]


def verticals_for(vendor: str, tiers: tuple[str, ...] = (CORE, SECONDARY, DEFER)) -> list[dict]:
    """Return the vendor's verticals (best-first) filtered to the given tiers.

    Each item: {slug, name, focus, example_reseller_software, tier}.
    """
    keep = set(tiers)
    out: list[dict] = []
    for slug, tier in VENDOR_VERTICALS.get((vendor or "").strip(), []):
        if tier in keep:
            out.append({**VERTICAL_PRESETS[slug], "slug": slug, "tier": tier})
    return out


def exclusions_for(vendor: str) -> dict[str, list[str]]:
    """Return the competitor→locked-tiers exclusion map for a vendor."""
    return dict(VENDOR_EXCLUSIONS.get((vendor or "").strip(), {}))


def exclusion_note(vendor: str) -> str:
    """English info-chip text describing which resellers are excluded, or ''."""
    ex = VENDOR_EXCLUSIONS.get((vendor or "").strip())
    if not ex:
        return ""
    parts = []
    for competitor, tiers in ex.items():
        if tiers == ["exclusive"]:
            parts.append(f"{competitor}-exclusive partners")
        else:
            parts.append(f"{competitor} {'/'.join(tiers)}")
    return ("Excludes the vendor's own subsidiaries and competitors' locked partners: "
            + ", ".join(parts) + ".")


def discover_verticals(vendor: str, slugs: list[str] | None = None,
                       tiers: tuple[str, ...] = (CORE, SECONDARY)) -> list[dict]:
    """Build Vertical-ready dicts for a discover campaign.

    If `slugs` is given, keep exactly those (in the vendor's catalogue order);
    otherwise take the vendor's verticals in `tiers`. Maps the preset's
    ``example_reseller_software`` to the Vertical model's ``example_software``.
    """
    if slugs is not None:
        wanted = set(slugs)
        picked = [v for v in verticals_for(vendor, tiers=TIERS) if v["slug"] in wanted]
    else:
        picked = verticals_for(vendor, tiers=tiers)
    return [{
        "name": v["name"],
        "slug": v["slug"],
        "focus": v["focus"],
        "example_software": list(v["example_reseller_software"]),
    } for v in picked]


def _load_research_overlay() -> None:
    """Overlay research-sourced brands (gtm.tools.gen_landscape) onto the catalogue.

    ``landscape_brands.json`` (slug -> [brands]) is the web-researched source of
    truth for ``example_reseller_software``; the YAML lists are the fallback.
    """
    import json
    p = Path(__file__).with_name("landscape_brands.json")
    if not p.exists():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for slug, brands in data.items():
        if slug in VERTICAL_PRESETS and brands:
            VERTICAL_PRESETS[slug]["example_reseller_software"] = list(brands)


def _validate() -> None:
    for vendor, items in VENDOR_VERTICALS.items():
        seen: set[str] = set()
        for slug, tier in items:
            if slug not in VERTICAL_PRESETS:
                raise ValueError(f"{vendor}: unknown vertical slug '{slug}'")
            if tier not in TIERS:
                raise ValueError(f"{vendor}/{slug}: invalid tier '{tier}'")
            if slug in seen:
                raise ValueError(f"{vendor}: duplicate vertical '{slug}'")
            seen.add(slug)


_load_research_overlay()
_validate()
