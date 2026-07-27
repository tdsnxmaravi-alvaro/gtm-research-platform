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


def score_results(config: CampaignConfig, results: list[dict]) -> list[dict]:
    """Apply the LLM-evidence scoring (URL gate) to all results."""
    return [apply_url_gate(config, r) for r in results]


def deterministic_score(config: CampaignConfig, row: dict):
    """Placeholder for keyword/field scoring on structured discover data.

    Returns None unless dimensions define keyword rules (to be added when a
    discover-with-structured-fields campaign needs it; port from score_resellers.py).
    """
    return None
