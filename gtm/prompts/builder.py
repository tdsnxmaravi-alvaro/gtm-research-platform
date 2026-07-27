"""Prompt builder — compose a research prompt from a campaign config.

Selects the template by (target_type, mode, verticals) and injects product,
country, fit criteria, evidence rules (URL gate) and scoring. For `provided`
mode, pass the company/companies to qualify via `company_input`.
"""

from __future__ import annotations

from ..config.schema import CampaignConfig, Product, Vertical
from . import templates


def _fit_criteria_block(product: Product) -> str:
    if product.fit_criteria:
        return "\n".join(f"- {c}" for c in product.fit_criteria)
    return "- General fit for the product (assess capability/demand as relevant)."


def _scoring_block(config: CampaignConfig) -> str:
    dims = config.scoring.dimensions
    if dims:
        lines = [
            f"- {d.name} (max {d.max_points} pts)" + (f": {d.description}" if d.description else "")
            for d in dims
        ]
        dim_text = "\n".join(lines)
    else:
        dim_text = "- Overall fit (0-100)"
    tiers = " · ".join(f"{k} >= {v}" for k, v in config.scoring.tier_thresholds.items())
    return f"Dimensions:\n{dim_text}\nTiers (by total score): {tiers}"


def _evidence_block(config: CampaignConfig) -> str:
    return templates.EVIDENCE_RULES.format(tier_cap=config.scoring.unverified_tier_cap)


def format_companies(rows: list[dict], fields: tuple[str, ...] = ("company", "website")) -> str:
    """Render a list of company dicts into a numbered block for `provided` prompts."""
    out = []
    for i, r in enumerate(rows, 1):
        parts = [str(r.get(f, "")).strip() for f in fields]
        parts = [p for p in parts if p]
        out.append(f"{i}. " + " | ".join(parts))
    return "\n".join(out)


def build_prompt(
    config: CampaignConfig,
    product: Product,
    *,
    company_input: str | None = None,
    vertical: Vertical | None = None,
) -> str:
    """Build the final research prompt string for a campaign + product."""
    key = config.prompt_template_key()
    template = templates.TEMPLATES[key]
    ctx = {
        "product_name": product.name,
        "value_prop": product.value_prop or product.name,
        "country": config.country,
        "language": config.language or "en",
        "fit_criteria": _fit_criteria_block(product),
        "evidence_rules": _evidence_block(config),
        "scoring": _scoring_block(config),
        "output_schema": templates.OUTPUT_SCHEMA,
        "vertical_name": vertical.name if vertical else "",
        "company_input": company_input or "",
    }
    return template.format(**ctx)
