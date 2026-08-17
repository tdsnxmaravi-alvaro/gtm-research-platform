"""Ready-made per-vendor qualification presets.

Data lives in ``gtm/prompts/data/vendor_presets.yaml`` so onboarding a vendor is
a data change, not a code change. Each vendor carries a value proposition,
target-specific fit criteria and two vendor-specific scoring dimensions (~40 pts)
on top of the reusable universal dimensions (60 pts) from ``gtm.scoring.library``.
Country is not baked in — it stays a campaign variable injected by the prompt builder.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

VENDOR_PRESETS: dict[str, dict] = yaml.safe_load(
    (Path(__file__).parent / "data" / "vendor_presets.yaml").read_text(encoding="utf-8")
) or {}

# Scoring defaults shared by the presets (Trimble-style).
_TIER_THRESHOLDS = {"A": 80, "B": 65, "C": 50, "D": 0}
_UNVERIFIED_TIER_CAP = "C"


def _reseller_dimensions(vendor: str, sectors: str, domain: str) -> list[dict]:
    return [
        {
            "name": f"Customer-base fit for {vendor}",
            "max_points": 22,
            "description": f"How well the company's customers match {sectors}.",
            "anchors": [
                f"17-22: clear, evidenced base of {sectors} customers",
                "11-16: partial or plausible target-sector customer base",
                "4-10: mostly generic customers, weak sector signal",
                "0-3: no target-sector customers evidenced",
            ],
        },
        {
            "name": f"{domain} adjacency & capability",
            "max_points": 18,
            "description": f"Existing footprint selling/implementing {domain}.",
            "anchors": [
                f"14-18: already resells/implements {domain}",
                "8-13: adjacent software footprint or partial signal",
                "3-7: generic software only, no domain adjacency",
                "0-2: no relevant software-vendor adjacency evidenced",
            ],
        },
    ]


def _account_dimensions(vendor: str, sectors: str, domain: str) -> list[dict]:
    return [
        {
            "name": f"Demand fit for {vendor}",
            "max_points": 22,
            "description": f"Concrete, current need/triggers to adopt {domain}.",
            "anchors": [
                f"17-22: multiple current triggers to adopt {domain}",
                "11-16: at least one clear, recent demand trigger",
                "4-10: weak or indirect demand signal",
                "0-3: no verifiable demand signal",
            ],
        },
        {
            "name": f"{domain} adoption readiness",
            "max_points": 18,
            "description": f"Sector, size and maturity to adopt {domain}.",
            "anchors": [
                f"14-18: sector/size/maturity strongly match {domain}",
                "8-13: reasonable fit",
                "3-7: marginal fit",
                "0-2: poor fit",
            ],
        },
    ]


def preset_for(vendor: str, target_type: str = "resellers") -> dict | None:
    """Return a resolved preset for a vendor + target_type, or None if unknown.

    Keys: product_name, value_prop, fit_criteria (list[str]), dimensions (list),
    use_universal, tier_thresholds, unverified_tier_cap.
    """
    base = VENDOR_PRESETS.get((vendor or "").strip())
    if not base:
        return None
    is_accounts = str(target_type) in ("accounts", "TargetType.accounts")
    fit = base["account_fit"] if is_accounts else base["reseller_fit"]
    dims = (_account_dimensions if is_accounts else _reseller_dimensions)(
        vendor, base["sectors"], base["domain"]
    )
    return {
        "product_name": base["product_name"],
        "value_prop": base["value_prop"],
        "fit_criteria": list(fit),
        "dimensions": dims,
        "use_universal": True,
        "tier_thresholds": dict(_TIER_THRESHOLDS),
        "unverified_tier_cap": _UNVERIFIED_TIER_CAP,
    }


def enrich_config_dict(cfg: dict) -> dict:
    """Fill in vendor-preset defaults on a campaign config dict (non-destructive).

    Only fills fields the caller left empty: product value_prop / fit_criteria /
    name, and the scoring rubric (when no dimensions were supplied). Returns a new
    dict; the original is not mutated.
    """
    preset = preset_for(cfg.get("vendor", ""), cfg.get("target_type", "resellers"))
    if not preset:
        return cfg
    cfg = copy.deepcopy(cfg)

    products = cfg.get("products") or [{}]
    p0 = products[0] if products else {}
    if not p0.get("name"):
        p0["name"] = preset["product_name"]
    if not p0.get("value_prop"):
        p0["value_prop"] = preset["value_prop"]
    if not p0.get("fit_criteria"):
        p0["fit_criteria"] = preset["fit_criteria"]
    products[0] = p0
    cfg["products"] = products

    scoring = dict(cfg.get("scoring") or {})
    if not scoring.get("dimensions"):
        scoring["use_universal"] = True
        scoring["dimensions"] = preset["dimensions"]
        scoring.setdefault("tier_thresholds", preset["tier_thresholds"])
        scoring.setdefault("unverified_tier_cap", preset["unverified_tier_cap"])
        cfg["scoring"] = scoring

    return cfg
