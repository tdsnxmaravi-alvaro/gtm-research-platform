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
            "Trimble's channel software for design and the built environment, sold through "
            "TD SYNNEX / Datech: Tekla Structures, Tekla Structural Designer and Tekla Tedds "
            "(structural BIM, analysis, steel & concrete detailing); SketchUp (3D modeling); "
            "Trimble Connect (common data environment / cloud collaboration); Viewpoint and "
            "ProjectSight (construction & project management); and Quadri & Novapoint (civil "
            "infrastructure design). We recruit TD SYNNEX resellers who could ADD this design "
            "software to their portfolio — they need not sell design software today; the "
            "question is capability, services and customer base to do so successfully."
        ),
        "reseller_fit": [
            "Is a software-selling VAR (licensing, renewals, services), not a pure hardware / box-mover",
            "Serves design-intensive sectors: architecture, engineering, construction, "
            "manufacturing, industrial or creative/media",
            "Shows adjacency to design/CAD/BIM/engineering/creative software (Autodesk, Bentley, "
            "Nemetschek, PTC, Dassault, Adobe) — a strong plus, not a gate",
            "Provides value-added services a design line requires: training, technical support, "
            "implementation, certified staff",
            "Has established commercial presence and delivery capability in the target country",
            "Bonus: existing surveying / geospatial / civil-field footprint (Trimble Field Systems adjacency)",
        ],
        "account_fit": [
            "Runs active AEC / engineering / construction or civil-infrastructure projects that need BIM, 3D or a CDE",
            "Demand triggers: new project wins, hiring of designers/engineers/BIM staff, expansion, M&A",
            "Uses or is actively replacing competing CAD/BIM tools (Autodesk, Bentley, Nemetschek)",
            "Structural, civil or construction workflows that fit Tekla / Trimble Connect / Viewpoint",
        ],
    },
    "Bricsys": {
        "product_name": "BricsCAD",
        "domain": "DWG-native CAD (2D drafting, 3D, BIM, mechanical)",
        "sectors": "architecture, engineering, construction, manufacturing, industrial",
        "value_prop": (
            "BricsCAD (Bricsys, a Hexagon company) is a DWG-native CAD platform with full .dwg "
            "compatibility and familiar commands, offered in editions: BricsCAD Lite (2D drafting), "
            "Pro (2D + 3D modeling, LISP/BLADE automation and APIs), Mechanical (3D parts & assemblies), "
            "BIM (DWG-based building information modeling) and Ultimate (all combined) — plus Bricsys 24/7 "
            "for document/project collaboration. It runs on Windows, macOS and Linux, offers a "
            "perpetual-license option versus subscription-only AutoCAD, and delivers lower total cost — a "
            "credible AutoCAD alternative resellers can add without disrupting customers' CAD workflows."
        ),
        "reseller_fit": [
            "Sells CAD / design / engineering software with services (licensing + renewals + implementation), not hardware only",
            "Has customers in AEC, manufacturing or industrial design that work in DWG day to day",
            "Existing AutoCAD / Autodesk (or other CAD) footprint — a strong migration & cross-sell opportunity",
            "Provides training, deployment, LISP/API customization and technical support for CAD",
            "Can position perpetual-licensing / cost-savings and BIM or mechanical modules, not just 2D drafting",
            "Established commercial presence and delivery capability in the target country",
        ],
        "account_fit": [
            "Relies on DWG/CAD for drafting, design or documentation and faces AutoCAD subscription-cost pressure",
            "Demand triggers: CAD license renewals, drawing-standardization projects, hiring of drafters/engineers",
            "Runs manufacturing or AEC workflows needing 2D drafting, mechanical modeling or DWG-based BIM",
            "Manages large legacy DWG libraries that need cleanup / standardization",
        ],
    },
    "DraftSight": {
        "product_name": "DraftSight",
        "domain": "professional 2D/3D DWG CAD software",
        "sectors": "engineering, manufacturing, construction, AEC, facilities",
        "value_prop": (
            "DraftSight (Dassault Systèmes) is professional 2D drafting and 3D design on the native DWG "
            "format, in editions DraftSight Standard, Professional, Premium and Enterprise / Enterprise Plus "
            "(with network/flexible licensing and deployment tools), plus DraftSight Mechanical. It offers "
            "APIs and scripting (LISP, C++, .NET), perpetual and subscription options, and a cost-effective, "
            "familiar alternative to AutoCAD LT / AutoCAD for professional CAD users — easy for resellers to "
            "position into engineering, manufacturing and construction accounts."
        ),
        "reseller_fit": [
            "Sells CAD / design / engineering software with services, not a pure box-mover",
            "Serves engineering, manufacturing, construction or AEC customers who work in DWG",
            "CAD / AutoCAD-adjacent footprint (drafting, design tools, migrations) — a plus",
            "Can manage volume/network (Enterprise) licensing, deployment and standardization for larger accounts",
            "Offers training, deployment and support for professional CAD",
            "Established commercial presence in the target country",
        ],
        "account_fit": [
            "Uses professional 2D/3D CAD for drafting/design and is cost-sensitive on AutoCAD licensing",
            "Demand triggers: CAD renewals, new design headcount, drawing-standardization or fleet-deployment initiatives",
            "Runs engineering / manufacturing documentation workflows on DWG",
        ],
    },
    "Novade": {
        "product_name": "Novade",
        "domain": "construction & facilities field-operations SaaS",
        "sectors": "construction contractors, subcontractors, developers, facilities and infrastructure operators",
        "value_prop": (
            "Novade is a mobile-first cloud platform that digitizes construction and facilities site "
            "operations — Novade Quality (inspections, snagging/defects, ITPs), Safety (permits, "
            "toolbox, incidents), Progress / Site Diary (daily reports, labour & plant tracking), "
            "Maintenance and Activity/Workflow apps, with Novade Analytics dashboards and a lighter "
            "Novade Lite for SMEs. It replaces paper and WhatsApp on site and opens a recurring SaaS "
            "revenue line for resellers serving contractors and AEC/FM firms."
        ),
        "reseller_fit": [
            "Sells SaaS / cloud software with onboarding, configuration and customer success (recurring-revenue capable)",
            "Serves construction contractors, subcontractors, developers, facilities or infrastructure operators",
            "Adjacency to construction tech, field/mobile apps, BIM or project-management software — a plus",
            "Provides implementation, training, integration and ongoing customer-success services",
            "Established presence and delivery capability in the target country",
        ],
        "account_fit": [
            "Is a contractor / AEC / FM firm running active site operations still on paper, spreadsheets or WhatsApp",
            "Demand triggers: new project wins, safety/quality compliance pressure, ISO audits, digitization mandates",
            "Has field teams that would adopt mobile inspections, permits, defects/snagging or site-diary workflows",
        ],
    },
    "Newforma": {
        "product_name": "Newforma",
        "domain": "AEC project information management (PIM) software",
        "sectors": "architecture and engineering firms, general contractors, owners/operators",
        "value_prop": (
            "Newforma is project information management for AEC — Newforma Konekt (cloud information "
            "management and BIM issue/model coordination, the 'golden thread'), Newforma Project Center "
            "(email, documents, RFIs, submittals, transmittals and markups with Outlook/Revit/Bentley "
            "connectors) and Newforma ConstructEx (cloud construction administration & document control). "
            "It helps architecture, engineering and construction teams find project information fast, "
            "control RFIs/submittals and reduce liability — a sticky software line for resellers who serve design firms."
        ),
        "reseller_fit": [
            "Sells software and services to AEC firms (architects, engineers, general contractors, owners)",
            "Has a customer base of design/engineering firms or construction companies",
            "Adjacency to AEC/BIM/CAD (Revit, Bentley), document management or Outlook/M365 workflows — a plus",
            "Provides implementation, data migration, training and support for professional software",
            "Can sell both cloud (Konekt/ConstructEx) and hybrid/on-prem (Project Center)",
            "Established commercial presence in the target country",
        ],
        "account_fit": [
            "Is an architecture / engineering / construction firm managing many concurrent projects and documents",
            "Demand triggers: growth in project volume, RFI/submittal overload, BIM coordination needs, risk/liability or claims exposure",
            "Collaborates across disciplines and needs email/document/model information control and an audit trail",
        ],
    },
    "Unity": {
        "product_name": "Unity",
        "domain": "real-time 3D (RT3D) / visualization / digital-twin / AR-VR software",
        "sectors": "manufacturing, automotive, AEC visualization, media & entertainment, training/simulation",
        "value_prop": (
            "Unity is a real-time 3D platform for interactive experiences. Beyond games, Unity Industry "
            "(built on Unity Pro/Enterprise) targets non-game applications — industrial digital twins, "
            "product and AEC visualization, HMI, AR/VR, simulation and training — with Unity Cloud for "
            "build/asset management, Pixyz to import and optimize CAD/BIM/3D data for real-time, and Unity "
            "AI (Muse/Sentis). It publishes across desktop, mobile, web, AR and VR. Resellers can attach "
            "licensing plus 3D/development and integration services across manufacturing, automotive, AEC and media accounts."
        ),
        "reseller_fit": [
            "Sells software and/or 3D / application-development / integration services (not hardware only)",
            "Serves customers needing real-time 3D: digital twins, product/AEC visualization, AR/VR, HMI, simulation or training",
            "Adjacency to 3D / CAD / creative / real-time / game-engine tooling or Pixyz-style CAD data prep — a plus",
            "Provides development, integration, training and support capability (RT3D is services-led)",
            "Can engage industrial / enterprise accounts (Unity Industry) beyond individual creators",
            "Established commercial presence in the target country",
        ],
        "account_fit": [
            "Needs real-time 3D: digital twins, product/AEC viz, AR/VR, HMI, simulation or immersive training",
            "Demand triggers: new visualization/immersive/Industry-4.0 initiatives, 3D/XR hiring, R&D or innovation projects",
            "Owns CAD/BIM/3D data (Pixyz) that would benefit from interactive, real-time experiences",
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
