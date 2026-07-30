"""Ready-made per-vendor qualification presets.

Each vendor carries a value proposition, target-specific fit criteria and two
vendor-specific scoring dimensions (~40 pts) that sit on top of the reusable
universal dimensions (60 pts) from ``gtm.scoring.library``. Country is NOT baked
in here — it stays a campaign variable and is injected by the prompt builder.

The Trimble preset mirrors ``campaigns/trimble-iberia.yaml``; BricsCAD generalises
the legacy per-vertical BricsCAD framework; the rest follow the same shape and are
first drafts meant to be refined.
"""

from __future__ import annotations

import copy

# --------------------------------------------------------------------------- #
# Vendor descriptors. `sectors` + `domain` drive the generated specific
# dimensions so the two-dimension rubric stays consistent across vendors.
# --------------------------------------------------------------------------- #
VENDOR_PRESETS: dict[str, dict] = {
    "Trimble": {
        "product_name": "Trimble AEC & design software portfolio",
        "domain": "design / CAD / BIM / civil software",
        "sectors": "architecture, engineering, construction, surveying, manufacturing",
        "value_prop": (
            "Trimble's channel software for design and the built environment — Tekla "
            "(structural BIM/analysis), SketchUp (3D modeling), Trimble Connect (common "
            "data environment), Viewpoint/ProjectSight (construction management) and "
            "Quadri/Novapoint (civil infrastructure). We recruit resellers who can ADD "
            "this design software to their portfolio; they need not sell it today."
        ),
        "reseller_fit": [
            "Is a software-selling VAR (licensing, renewals, services), not a pure box-mover",
            "Serves design-intensive sectors: architecture, engineering, construction, "
            "manufacturing or creative/media",
            "Shows adjacency to design/CAD/BIM/engineering software (Autodesk, Bentley, "
            "Nemetschek, PTC, Dassault…) — a plus, not a gate",
            "Provides value-added services (training, support, implementation, certified staff)",
            "Has an established commercial presence and delivery capability in the target country",
        ],
        "account_fit": [
            "Runs active AEC/engineering/construction or civil projects that need BIM, 3D or CDE",
            "Shows demand triggers: new projects, hiring of designers/engineers, expansion, M&A",
            "Uses (or is replacing) competing CAD/BIM tools",
        ],
    },
    "Bricsys": {
        "product_name": "BricsCAD",
        "domain": "DWG-native CAD (2D/3D, BIM, mechanical)",
        "sectors": "architecture, engineering, construction, manufacturing",
        "value_prop": (
            "BricsCAD is a DWG-native CAD platform — full .dwg compatibility with familiar "
            "commands, 2D drafting, 3D direct modeling, BIM and mechanical modules, at a "
            "lower total cost and with a perpetual-license option versus subscription-only "
            "AutoCAD. A credible AutoCAD alternative resellers can add without disrupting "
            "their customers' CAD workflows."
        ),
        "reseller_fit": [
            "Sells CAD/design or engineering software (licensing + services), not hardware only",
            "Has customers in AEC, manufacturing or industrial design that run DWG workflows",
            "Existing AutoCAD/Autodesk or CAD adjacency (migrations, training) — a strong plus",
            "Provides training, implementation and technical support for design software",
            "Established presence and delivery capability in the target country",
        ],
        "account_fit": [
            "Relies on DWG/CAD for drafting, design or documentation and faces AutoCAD cost pressure",
            "Shows triggers: CAD license renewals, standardization projects, hiring of drafters/engineers",
            "Runs manufacturing/AEC workflows that need 2D drafting or mechanical/BIM modeling",
        ],
    },
    "DraftSight": {
        "product_name": "DraftSight",
        "domain": "professional 2D/3D DWG CAD software",
        "sectors": "engineering, manufacturing, construction, AEC",
        "value_prop": (
            "DraftSight (Dassault Systèmes) is professional 2D drafting and 3D design on the "
            "native DWG format, with flexible perpetual and subscription licensing — a "
            "cost-effective alternative to AutoCAD LT for professional CAD users, easy for "
            "resellers to position into engineering and manufacturing accounts."
        ),
        "reseller_fit": [
            "Sells CAD/design or engineering software with services, not a pure box-mover",
            "Serves engineering, manufacturing, construction or AEC customers using DWG",
            "CAD/AutoCAD-adjacent footprint (drafting, design tools) — a plus",
            "Offers training, deployment and support for professional CAD",
            "Established commercial presence in the target country",
        ],
        "account_fit": [
            "Uses professional 2D/3D CAD for drafting/design and is cost-sensitive on licensing",
            "Demand triggers: CAD renewals, new design headcount, standardization initiatives",
            "Runs engineering/manufacturing documentation workflows on DWG",
        ],
    },
    "Novade": {
        "product_name": "Novade",
        "domain": "construction field-operations / site management SaaS",
        "sectors": "construction contractors, AEC, facilities and infrastructure",
        "value_prop": (
            "Novade is a cloud platform that digitizes construction site operations — quality "
            "inspections, safety, site diary, defects and workforce management on mobile. It "
            "opens a recurring SaaS revenue line for resellers serving contractors and AEC firms."
        ),
        "reseller_fit": [
            "Sells SaaS/cloud software with onboarding and support (recurring-revenue capable)",
            "Serves construction contractors, AEC firms, facilities or infrastructure operators",
            "Adjacency to construction tech / field apps / project management software — a plus",
            "Provides implementation, training and customer-success services",
            "Established presence and delivery capability in the target country",
        ],
        "account_fit": [
            "Is a contractor/AEC firm running active site operations that are still paper/manual",
            "Demand triggers: new projects, safety/quality compliance pressure, digitization drive",
            "Has field teams that would adopt mobile inspections, defects or site-diary workflows",
        ],
    },
    "Newforma": {
        "product_name": "Newforma",
        "domain": "AEC project information management (PIM) software",
        "sectors": "architecture and engineering firms, construction",
        "value_prop": (
            "Newforma is project information management for AEC — it organizes project email, "
            "documents, RFIs, submittals and markups so architecture, engineering and "
            "construction teams find information fast and reduce risk. A sticky software line "
            "for resellers who serve design firms."
        ),
        "reseller_fit": [
            "Sells software and services to AEC firms (architects, engineers, construction)",
            "Has a customer base of design/engineering firms or construction companies",
            "Adjacency to AEC/BIM/CAD or document-management software — a plus",
            "Provides implementation, training and support for professional software",
            "Established commercial presence in the target country",
        ],
        "account_fit": [
            "Is an architecture/engineering/construction firm managing many projects and documents",
            "Demand triggers: growth in project volume, RFI/submittal overload, risk/compliance needs",
            "Collaborates across teams and needs email/document/project information control",
        ],
    },
    "Unity": {
        "product_name": "Unity",
        "domain": "real-time 3D / visualization / AR-VR software",
        "sectors": "manufacturing, AEC visualization, automotive, media, training",
        "value_prop": (
            "Unity is a real-time 3D platform for interactive experiences — industrial digital "
            "twins, AEC and product visualization, AR/VR, simulation and training. Resellers "
            "can attach development services and licensing across manufacturing, automotive, "
            "AEC and media accounts."
        ),
        "reseller_fit": [
            "Sells software and/or 3D/development services (not hardware only)",
            "Serves customers needing 3D visualization, simulation, AR/VR or digital twins",
            "Adjacency to 3D/CAD/creative/real-time or game-engine tooling — a plus",
            "Provides development, integration, training and support capabilities",
            "Established commercial presence in the target country",
        ],
        "account_fit": [
            "Needs real-time 3D: digital twins, product/AEC viz, AR/VR, simulation or training",
            "Demand triggers: new visualization/immersive initiatives, 3D/dev hiring, R&D projects",
            "Owns 3D/CAD data that would benefit from interactive, real-time experiences",
        ],
    },
}

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
