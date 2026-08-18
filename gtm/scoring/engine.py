"""Scoring — turn research results into final tiers, enforcing the evidence URL gate.

Two paths:
- llm_evidence: the LLM already scored + tiered each company; we normalize the tier
  (derive from score if missing) and apply the HARD URL gate (no verified source URL
  -> tier capped at `unverified_tier_cap`).
- deterministic: keyword/field scoring for `discover` runs with structured data
  (generalized from the legacy score_resellers.py). Optional; used when dimensions
  carry keyword rules. Returns None if not configured.
"""

from __future__ import annotations

import re

from ..config.schema import CampaignConfig


def tier_order(config: CampaignConfig) -> list[str]:
    """Tiers best -> worst, derived from thresholds (e.g. ['A','B','C','D'])."""
    return [k for k, _ in sorted(config.scoring.tier_thresholds.items(),
                                 key=lambda kv: kv[1], reverse=True)]


def tier_from_score(config: CampaignConfig, score) -> str:
    order = tier_order(config)
    try:
        s = int(score)
    except (TypeError, ValueError):
        return order[-1]
    for tier in order:  # best -> worst
        if s >= config.scoring.tier_thresholds[tier]:
            return tier
    return order[-1]


def _cap_tier(tier: str, cap: str, order: list[str]) -> str:
    """A tier cannot be BETTER than `cap`."""
    if tier not in order or cap not in order:
        return tier
    return cap if order.index(tier) < order.index(cap) else tier


def apply_url_gate(config: CampaignConfig, result: dict) -> dict:
    """Set final_tier, applying the evidence URL gate. Mutates + returns result."""
    order = tier_order(config)
    tier = (result.get("tier") or "").strip().upper()
    if tier not in order:
        tier = tier_from_score(config, result.get("score"))

    final = tier
    reason = ""
    if not result.get("has_verified_url"):
        final = _cap_tier(tier, config.scoring.unverified_tier_cap, order)
        if final != tier:
            reason = f"no verified URL -> capped at {config.scoring.unverified_tier_cap}"

    result["tier"] = tier
    result["final_tier"] = final
    result["tier_capped"] = bool(reason)
    result["tier_cap_reason"] = reason
    return result


def _is_captive(result: dict) -> bool:
    """A reseller flagged Subsidiary/Acquired is not an independent channel partner."""
    return str(result.get("independence") or "").strip().lower() in ("subsidiary", "acquired")


def _negated_competitor(hay: str, competitor: str) -> bool:
    """True when the competitor is mentioned in a negation (do not treat as locked)."""
    c = re.escape(competitor.lower())
    return bool(re.search(
        rf"\b(?:not|no|never|without)\b(?:\s+\w+){{0,5}}\s+{c}"
        rf"|{c}\s+(?:\w+\s+){{0,3}}(?:not|never)\b",
        hay,
    ))


def _excluded_partner(config: CampaignConfig, result: dict) -> str:
    """Return the competitor name if the reseller looks locked to an excluded competitor.

    Safety net for the prompt's EXCLUSIONS: scans the reseller's resold-software /
    notes / fit text for a competitor from VENDOR_EXCLUSIONS together with one of its
    locked tier keywords (e.g. 'Autodesk' + 'Gold', or an 'exclusive' lock cue).
    """
    from ..prompts.vertical_presets import VENDOR_EXCLUSIONS
    ex = VENDOR_EXCLUSIONS.get((config.vendor or "").strip())
    if not ex:
        return ""
    hay = " ".join(str(result.get(f, "")) for f in
                   ("software_resold", "notes", "fit_summary")).lower()
    for competitor, levels in ex.items():
        if competitor.lower() not in hay:
            continue
        if _negated_competitor(hay, competitor):
            continue
        if levels == ["exclusive"]:
            cues = ("exclusive", "exclusively", "locked", "only reseller", "sole reseller")
        else:
            cues = tuple(level.lower() for level in levels)
        if any(c in hay for c in cues):
            return competitor
    return ""


def apply_exclusion_gates(config: CampaignConfig, result: dict) -> dict:
    """Cap final_tier for non-independent or competitor-locked resellers (all modes)."""
    order = tier_order(config)
    final = (result.get("final_tier") or result.get("tier")
             or tier_from_score(config, result.get("score")))
    reasons = []

    if _is_captive(result):
        capped = _cap_tier(final, config.scoring.captive_tier_cap, order)
        if capped != final:
            reasons.append(f"non-independent -> capped at {config.scoring.captive_tier_cap}")
            final = capped

    competitor = _excluded_partner(config, result)
    if competitor:
        capped = _cap_tier(final, config.scoring.excluded_partner_tier_cap, order)
        if capped != final:
            reasons.append(f"{competitor}-locked partner -> capped at "
                           f"{config.scoring.excluded_partner_tier_cap}")
            final = capped

    if reasons:
        result["final_tier"] = final
        result["tier_capped"] = True
        prev = result.get("tier_cap_reason") or ""
        result["tier_cap_reason"] = "; ".join([r for r in (prev,) if r] + reasons)
    return result


def score_results(config: CampaignConfig, results: list[dict]) -> list[dict]:
    """Apply the LLM-evidence scoring (URL gate) plus exclusion gates (captive /
    competitor-locked) in every mode — we never want to contact a reseller locked
    to an excluded competitor, whether the list was discovered or provided."""
    out = [apply_url_gate(config, r) for r in results]
    return [apply_exclusion_gates(config, r) for r in out]


def deterministic_score(config: CampaignConfig, row: dict):
    """Placeholder for keyword/field scoring on structured discover data.

    Returns None unless dimensions define keyword rules (to be added when a
    discover-with-structured-fields campaign needs it; port from score_resellers.py).
    """
    return None
