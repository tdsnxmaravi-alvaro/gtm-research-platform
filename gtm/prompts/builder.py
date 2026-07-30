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
        lines = []
        for d in dims:
            head = f"- {d.name} (max {d.max_points} pts)"
            if d.description:
                head += f": {d.description}"
            lines.append(head)
            for a in d.anchors:
                lines.append(f"    · {a}")
        dim_text = "\n".join(lines)
        total = config.scoring.total_max_points()
    else:
        dim_text = "- Overall fit (0-100)"
        total = 100
    tiers = " · ".join(f"{k} >= {v}" for k, v in config.scoring.tier_thresholds.items())
    return (
        f"Score each dimension against its point-band anchors (total {total} pts):\n"
        f"{dim_text}\nTiers (by total score): {tiers}"
    )


def _evidence_block(config: CampaignConfig) -> str:
    return templates.EVIDENCE_RULES.format(tier_cap=config.scoring.unverified_tier_cap)


# Sentinel injected into a previewed/edited prompt where the provided companies
# will be spliced in at run time (companies aren't known when editing the prompt).
COMPANIES_TOKEN = "[[COMPANIES]]"


def format_companies(
    rows: list[dict],
    fields: tuple[str, ...] = ("company", "website"),
    context_fields: tuple[str, ...] = ("country", "other software in use", "company size"),
) -> str:
    """Render a list of company dicts into a numbered block for `provided` prompts.

    `fields` are shown plainly (company | website). `context_fields` are appended
    as labeled hints when present (e.g. the reseller's own country and current
    software portfolio), so the model qualifies each company in its own country.
    """
    out = []
    for i, r in enumerate(rows, 1):
        parts = [str(r.get(f, "")).strip() for f in fields]
        parts = [p for p in parts if p]
        line = f"{i}. " + " | ".join(parts)
        extras = []
        for cf in context_fields:
            v = str(r.get(cf, "")).strip()
            if v:
                extras.append(f"{cf}: {v}")
        if extras:
            line += "  [" + "; ".join(extras) + "]"
        out.append(line)
    return "\n".join(out)


def build_prompt(
    config: CampaignConfig,
    product: Product,
    *,
    company_input: str | None = None,
    vertical: Vertical | None = None,
) -> str:
    """Build the final research prompt string for a campaign + product."""
    # Explicit user-edited prompt (from the wizard prompt builder) wins over the
    # template. Splice the provided companies into the sentinel when running.
    if product.search_prompt:
        base = product.search_prompt
        if company_input is not None:
            base = base.replace(COMPANIES_TOKEN, company_input)
        return base
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
        "company_input": company_input if company_input is not None else COMPANIES_TOKEN,
    }
    return template.format(**ctx)
