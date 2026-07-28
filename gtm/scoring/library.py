"""Reusable, vendor/vertical-agnostic scoring dimensions (the universal rubric).

Ported in spirit from the legacy score_resellers.py "universal dimensions" idea:
a fixed set of channel-fit dimensions that apply to ANY vendor and ANY vertical,
each with concrete point-band anchors. A campaign turns these on with
`scoring.use_universal: true` and then adds its own product/vertical-specific
dimensions. Keeping the total at 100 points is the convention.

RESELLER universals (60 pts) assess whether a partner can SELL the product;
ACCOUNT universals (60 pts) assess buy/use readiness. The remaining ~40 pts are
the campaign's specific dimensions.
"""

from __future__ import annotations

UNIVERSAL_RESELLER_DIMENSIONS = [
    {
        "name": "Software VAR capability & services",
        "max_points": 22,
        "description": "Is it a genuine software reseller/VAR able to take on a new vendor?",
        "anchors": [
            "18-22: mature software VAR — licensing, renewals, training, "
            "implementation and support with certified staff",
            "12-17: sells software with some services (onboarding/support)",
            "6-11: mostly resells/box-moves software, thin services",
            "0-5: hardware/box-mover, pure e-tailer, or no software resale",
        ],
    },
    {
        "name": "Portfolio breadth & vendor-onboarding capacity",
        "max_points": 18,
        "description": "Diversity of vendors/lines and maturity to add & grow a new line.",
        "anchors": [
            "14-18: many vendors, structured onboarding/marketing, proven cross-sell",
            "9-13: several lines, some multi-vendor management",
            "4-8: narrow portfolio, limited capacity to add a line",
            "0-3: single-line or no evidence of vendor management",
        ],
    },
    {
        "name": "Market presence & momentum in target geography",
        "max_points": 20,
        "description": "Established local operation, coverage, recent growth/hiring/events.",
        "anchors": [
            "15-20: established, multi-region coverage, clear 2024-2026 growth signals",
            "9-14: solid local presence, some recent activity",
            "4-8: small/local footprint, little recent momentum",
            "0-3: minimal or unverifiable presence in the geography",
        ],
    },
]

UNIVERSAL_ACCOUNT_DIMENSIONS = [
    {
        "name": "Active demand signals",
        "max_points": 24,
        "description": "Concrete triggers to buy/use the product now.",
        "anchors": [
            "18-24: multiple current triggers (active projects, hiring, expansion, M&A)",
            "11-17: at least one clear, recent demand trigger",
            "4-10: weak/indirect signals",
            "0-3: no verifiable demand signal",
        ],
    },
    {
        "name": "Organizational fit & capacity",
        "max_points": 18,
        "description": "Size, sector and maturity to adopt the product.",
        "anchors": [
            "14-18: sector, size and maturity strongly match the product",
            "9-13: reasonable fit",
            "4-8: marginal fit",
            "0-3: poor fit",
        ],
    },
    {
        "name": "Market presence & momentum in target geography",
        "max_points": 18,
        "description": "Established local operation and recent momentum.",
        "anchors": [
            "14-18: established, growing, active in the geography",
            "8-13: solid presence",
            "3-7: limited footprint",
            "0-2: minimal or unverifiable",
        ],
    },
]


def universal_dimensions(target_type: str) -> list[dict]:
    """Return the reusable universal dimensions for a target_type."""
    if str(target_type) in ("accounts", "TargetType.accounts"):
        return [dict(d) for d in UNIVERSAL_ACCOUNT_DIMENSIONS]
    return [dict(d) for d in UNIVERSAL_RESELLER_DIMENSIONS]
