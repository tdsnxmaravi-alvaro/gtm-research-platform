"""Vendor-native reseller verticals for DISCOVER mode.

When no company list is provided, discover mode proposes, per vendor, the reseller
verticals worth recruiting from — categories of resellers/VARs/integrators whose
existing portfolio and customers make them strong candidates to ADD the vendor's
product. Verticals were consolidated from a multi-LLM + web panel scored on three
axes (fit / searchable population / switchability) and tiered:

    core      — recommended, checked by default in the wizard
    secondary — available, checked by default
    defer     — shown but UNCHECKED (low priority / competitor-locked / niche)

`VENDOR_EXCLUSIONS` captures competitors whose LOCKED top-tier partners are excluded
(they won't add a competing line). This is surfaced to the user as an info chip and
is applied by the discover prompt + scoring.
"""

from __future__ import annotations

# Tier constants (ordered best-first).
CORE = "core"
SECONDARY = "secondary"
DEFER = "defer"
TIERS = (CORE, SECONDARY, DEFER)

# --------------------------------------------------------------------------- #
# Vertical catalogue — one entry per distinct reseller pool (reused across
# vendors). `example_reseller_software` lists brands such resellers already sell.
# --------------------------------------------------------------------------- #
VERTICAL_PRESETS: dict[str, dict] = {
    # --- AEC / construction design & field --------------------------------- #
    "autodesk-aec-vars": {
        "name": "Autodesk AEC/BIM VARs (Revit/Civil 3D/ACC)",
        "focus": "Resellers of the Autodesk AEC stack serving architects, engineers and GCs.",
        "example_reseller_software": ["Autodesk Revit", "AutoCAD", "Civil 3D", "Navisworks", "Autodesk Construction Cloud"],
    },
    "civil-infrastructure": {
        "name": "Civil infrastructure / road design resellers",
        "focus": "Resellers of civil/road/rail design software serving infrastructure engineers.",
        "example_reseller_software": ["Bentley OpenRoads", "Autodesk Civil 3D", "Carlson", "12d Model"],
    },
    "geospatial-survey": {
        "name": "Surveying / GIS / reality-capture geospatial dealers",
        "focus": "Dealers of GNSS, survey, scanning and GIS software serving surveyors and mappers.",
        "example_reseller_software": ["Leica", "Topcon", "Esri ArcGIS", "Pix4D", "Trimble Business Center"],
    },
    "structural-steel-detailing": {
        "name": "Structural steel/precast detailing & fabrication resellers",
        "focus": "Resellers of structural detailing/analysis/fabrication software for steel & precast.",
        "example_reseller_software": ["SDS2", "Advance Steel", "IDEA StatiCa", "Tekla PowerFab"],
    },
    "construction-erp-pm": {
        "name": "Construction ERP / project-management resellers",
        "focus": "Resellers of contractor ERP, accounting, scheduling and project-management software.",
        "example_reseller_software": ["Sage 300 CRE", "Viewpoint Vista", "Procore", "Oracle Primavera P6"],
    },
    "archviz-rendering": {
        "name": "Architectural visualization / rendering resellers (SketchUp ecosystem)",
        "focus": "Resellers of rendering/visualization tools serving architects and designers.",
        "example_reseller_software": ["Enscape", "Chaos V-Ray", "Twinmotion", "Lumion", "D5 Render"],
    },
    "cde-bim-coordination": {
        "name": "CDE / BIM coordination / document-management resellers",
        "focus": "Resellers of common-data-environment, markup and BIM-coordination tools for AEC.",
        "example_reseller_software": ["Bluebeam Revu", "Autodesk Docs", "Revizto", "Bentley ProjectWise"],
    },
    "contech-management": {
        "name": "Construction management / ConTech resellers (Procore/ACC)",
        "focus": "Implementers of construction-management platforms serving GCs and subcontractors.",
        "example_reseller_software": ["Procore", "Autodesk Construction Cloud", "PlanGrid", "Fieldwire"],
    },
    "mep-building-services": {
        "name": "MEP / building-services design resellers",
        "focus": "Resellers of MEP design/detailing software for building-services engineers.",
        "example_reseller_software": ["MagiCAD", "Trimble Stabicad", "Autodesk Revit MEP", "AX3000"],
    },
    "estimating-takeoff": {
        "name": "Estimating & takeoff software resellers",
        "focus": "Resellers of preconstruction estimating and quantity-takeoff tools.",
        "example_reseller_software": ["Bluebeam Revu", "PlanSwift", "Trimble WinEst", "STACK"],
    },
    "interior-woodworking": {
        "name": "Interior design / furniture / woodworking CAD resellers (SketchUp)",
        "focus": "Resellers of interior/kitchen/cabinetry design software.",
        "example_reseller_software": ["SketchUp", "Chief Architect", "2020 Design", "Cabinet Vision"],
    },
    "field-machine-control": {
        "name": "Construction field-technology / machine-control / drone integrators",
        "focus": "Integrators of positioning, machine-control, layout and UAV field technology.",
        "example_reseller_software": ["Topcon", "Leica", "DroneDeploy", "Pix4D"],
    },
    "aec-it-msp": {
        "name": "AEC-focused IT MSPs / Microsoft 365 / SharePoint integrators",
        "focus": "Managed-service providers running IT/M365 for architecture & engineering firms.",
        "example_reseller_software": ["Microsoft 365", "SharePoint", "Egnyte", "Panzura"],
    },
    "aec-realtime-viz": {
        "name": "AEC / architectural real-time visualization resellers",
        "focus": "Resellers of real-time viz/VR walkthrough tools for AEC firms.",
        "example_reseller_software": ["Enscape", "Twinmotion", "SketchUp", "Autodesk Revit"],
    },

    # --- AEC project information / document control (Newforma) -------------- #
    "aeco-document-control": {
        "name": "AECO document control / PIM / CDE resellers (ProjectWise, Aconex, ISO 19650)",
        "focus": "Resellers of project-information and document-control platforms for AEC.",
        "example_reseller_software": ["Bentley ProjectWise", "Oracle Aconex", "Asite", "Thinkproject"],
    },
    "bim-coordination-clash": {
        "name": "BIM coordination / clash-detection resellers (Navisworks/Revizto/Solibri)",
        "focus": "Resellers of model-review and clash-detection tools for VDC/coordination teams.",
        "example_reseller_software": ["Navisworks", "Revizto", "Solibri", "BIMcollab"],
    },
    "bluebeam-markup": {
        "name": "Bluebeam / PDF markup & document-collaboration resellers",
        "focus": "Resellers of PDF markup and document-collaboration tools for AEC.",
        "example_reseller_software": ["Bluebeam Revu", "Adobe Acrobat", "PlanGrid"],
    },
    "acc-procore-integrators": {
        "name": "Autodesk Construction Cloud / Procore integrators",
        "focus": "Implementers/integrators of ACC/BIM 360/Procore for construction teams.",
        "example_reseller_software": ["Autodesk Build", "Procore", "BIM 360", "PlanGrid"],
    },
    "m365-aec-it": {
        "name": "Microsoft 365 / SharePoint / Outlook AEC IT partners",
        "focus": "Microsoft partners specialized in architecture/engineering firms.",
        "example_reseller_software": ["Microsoft 365", "SharePoint", "Outlook", "Microsoft Teams"],
    },
    "aeco-msp": {
        "name": "AECO MSPs / cloud-migration / IT-infrastructure VARs",
        "focus": "MSPs migrating and managing AEC firms' file servers and cloud infrastructure.",
        "example_reseller_software": ["Microsoft Azure", "Egnyte", "Box", "Panzura"],
    },
    "construction-admin": {
        "name": "Construction administration / RFI-submittal / GC ConTech resellers",
        "focus": "Resellers of RFI/submittal/CA workflow tools for general contractors.",
        "example_reseller_software": ["Procore", "Autodesk Build", "Oracle Aconex", "CMiC"],
    },
    "design-authoring-addins": {
        "name": "Design-authoring add-in resellers (Revit/Navisworks/Archicad/Tekla/Rhino)",
        "focus": "Resellers of design-authoring add-ins/extensions to the AEC modeling ecosystem.",
        "example_reseller_software": ["Autodesk Revit", "Navisworks", "Graphisoft Archicad", "Tekla", "Rhino"],
    },
    "bentley-infrastructure": {
        "name": "Bentley / infrastructure-information resellers",
        "focus": "Resellers of Bentley infrastructure design and information tools.",
        "example_reseller_software": ["MicroStation", "OpenRoads", "ProjectWise", "SYNCHRO"],
    },
    "aec-elearning": {
        "name": "AEC e-learning / knowledge-management providers",
        "focus": "Providers of training/knowledge-management for AEC software users.",
        "example_reseller_software": ["Pinnacle Series", "KnowledgeSmart"],
    },
    "enterprise-crm": {
        "name": "Enterprise CRM / workflow-automation developers",
        "focus": "Developers/integrators of CRM and workflow automation for the enterprise.",
        "example_reseller_software": ["Salesforce", "Microsoft Dynamics 365"],
    },

    # --- CAD / manufacturing ---------------------------------------------- #
    "autocad-alternative": {
        "name": "AutoCAD / AutoCAD LT & DWG-alternative CAD VARs",
        "focus": "Resellers of DWG CAD serving customers seeking a lower-cost/perpetual alternative.",
        "example_reseller_software": ["AutoCAD", "AutoCAD LT", "ZWCAD", "GstarCAD", "ARES Commander"],
    },
    "mechanical-mcad": {
        "name": "Mechanical / manufacturing MCAD & CAM resellers",
        "focus": "Resellers of 3D mechanical CAD/CAM serving manufacturers and job shops.",
        "example_reseller_software": ["SOLIDWORKS", "Autodesk Inventor", "Solid Edge", "PTC Creo"],
    },
    "plant-process": {
        "name": "Plant / process design resellers (CADWorx / P&ID)",
        "focus": "Resellers of plant/process/piping design software serving EPC and industrial firms.",
        "example_reseller_software": ["Hexagon CADWorx", "AVEVA E3D", "AutoCAD Plant 3D", "CAESAR II"],
    },
    "civil-survey": {
        "name": "Civil engineering & surveying application resellers",
        "focus": "Resellers of civil/survey CAD add-ons serving surveyors and civil engineers.",
        "example_reseller_software": ["Carlson Software", "Civil Site Design", "MicroSurvey", "Autodesk Civil 3D"],
    },
    "aec-bim-alternative": {
        "name": "AEC / BIM / architecture resellers (Revit/ArchiCAD alternative)",
        "focus": "Resellers of BIM authoring tools serving architects open to a DWG-native option.",
        "example_reseller_software": ["Autodesk Revit", "Graphisoft Archicad", "Vectorworks", "Allplan"],
    },
    "cam-machining": {
        "name": "CAM software resellers",
        "focus": "Resellers of CNC/CAM software serving machine shops that need CAD upstream.",
        "example_reseller_software": ["Mastercam", "hyperMILL", "SolidCAM", "ESPRIT"],
    },
    "sheet-metal-nesting": {
        "name": "Nesting & sheet-metal software resellers",
        "focus": "Resellers of nesting/sheet-metal programming software serving fabricators.",
        "example_reseller_software": ["SigmaNEST", "Lantek", "Radan", "Trumpf"],
    },
    "reality-capture": {
        "name": "3D scanning / reality-capture resellers",
        "focus": "Resellers of laser scanning, photogrammetry and point-cloud software/hardware.",
        "example_reseller_software": ["Leica", "FARO", "Matterport", "NavVis"],
    },
    "cad-interop": {
        "name": "CAD interoperability / translation resellers",
        "focus": "Resellers of multi-CAD translation/interoperability tools.",
        "example_reseller_software": ["Elysium", "TransMagic", "Datakit", "Theorem"],
    },
    "gis-geospatial": {
        "name": "GIS & geospatial application resellers",
        "focus": "Resellers of GIS/mapping software serving utilities, government and infrastructure.",
        "example_reseller_software": ["Esri ArcGIS", "Hexagon", "Safe FME", "Bentley Map"],
    },
    "cafm-iwms": {
        "name": "Facilities / CAFM / IWMS resellers",
        "focus": "Resellers of facilities/space-management software using DWG floor plans.",
        "example_reseller_software": ["Planon", "Archibus", "IBM TRIRIGA", "FM:Systems"],
    },
    "ecad-electrical": {
        "name": "Electrical CAD (ECAD) resellers",
        "focus": "Resellers of electrical schematic/panel-design software.",
        "example_reseller_software": ["EPLAN", "Zuken", "WSCAD", "SEE Electrical"],
    },
    "additive-manufacturing": {
        "name": "Additive manufacturing resellers",
        "focus": "Resellers of 3D-printing software and hardware serving product designers.",
        "example_reseller_software": ["Stratasys", "Markforged", "Materialise", "Formlabs"],
    },
    "cae-simulation": {
        "name": "Engineering simulation (CAE) resellers",
        "focus": "Resellers of FEA/CFD simulation software serving analysts and engineers.",
        "example_reseller_software": ["Ansys", "Altair", "COMSOL", "MSC Software"],
    },
    "mes-digital-twin": {
        "name": "MES / digital twin resellers",
        "focus": "Integrators of MES/digital-twin platforms for manufacturing operations.",
        "example_reseller_software": ["Siemens Opcenter", "Rockwell", "PTC ThingWorx", "AVEVA"],
    },
    "cad-app-developers": {
        "name": "CAD application developers / customization consultancies",
        "focus": "Developers/consultancies building CAD add-ins, automation and vertical toolsets.",
        "example_reseller_software": ["AutoLISP / .NET add-ins", "BRX apps", "drawing automation"],
    },
    "solidworks-vars": {
        "name": "SOLIDWORKS / Dassault VARs",
        "focus": "Dassault/SOLIDWORKS resellers serving the manufacturing customer base.",
        "example_reseller_software": ["SOLIDWORKS", "SOLIDWORKS PDM", "3DEXPERIENCE", "CATIA"],
    },
    "pdm-plm": {
        "name": "PDM / PLM / engineering document-management resellers",
        "focus": "Resellers of product data / lifecycle management to engineering organizations.",
        "example_reseller_software": ["SOLIDWORKS PDM", "Aras", "Siemens Teamcenter", "PTC Windchill"],
    },
    "aec-2d-cad": {
        "name": "AEC / architectural 2D CAD resellers",
        "focus": "Resellers of affordable 2D DWG CAD for architects and drafters.",
        "example_reseller_software": ["AutoCAD Architecture", "Autodesk Revit", "SketchUp", "Bluebeam"],
    },
    "broadline-it": {
        "name": "Broadline IT / StreamOne distributors",
        "focus": "Volume IT resellers transacting CAD via open distribution (no deep CAD expertise).",
        "example_reseller_software": ["Microsoft 365", "Adobe Creative Cloud", "general IT software"],
    },
    "education-academic": {
        "name": "Education / academic resellers",
        "focus": "Academic/EdTech resellers delivering licensing, curricula and certification.",
        "example_reseller_software": ["Autodesk Education", "Adobe CC for Education", "Ansys Academic"],
    },
    "technical-comms": {
        "name": "Technical communication / documentation consultants",
        "focus": "Consultants producing technical illustrations and documentation from CAD.",
        "example_reseller_software": ["SOLIDWORKS Composer", "Adobe FrameMaker"],
    },

    # --- Construction field ops / facilities (Novade) ---------------------- #
    "ehs-safety": {
        "name": "EHS / safety / permit-to-work software resellers",
        "focus": "Resellers of EHS/safety-compliance software serving contractors and operators.",
        "example_reseller_software": ["Intelex", "EcoOnline", "VelocityEHS", "SafetyCulture"],
    },
    "quality-inspection": {
        "name": "Quality management / inspection / snagging software resellers",
        "focus": "Resellers of QA/QC, inspection and snagging software for construction.",
        "example_reseller_software": ["ETQ Reliance", "SafetyCulture", "Procore Quality & Safety"],
    },
    "cmms-eam": {
        "name": "CMMS / EAM / maintenance software resellers",
        "focus": "Resellers of maintenance/asset-management software serving owners and operators.",
        "example_reseller_software": ["IBM Maximo", "Infor EAM", "Fiix", "MaintainX"],
    },
    "field-punchlist": {
        "name": "Construction field / punch-list / drawings resellers",
        "focus": "Resellers of mobile field-issue and drawing apps for site teams.",
        "example_reseller_software": ["Fieldwire", "Dalux", "PlanGrid", "Bluebeam"],
    },
    "heavy-civil": {
        "name": "Heavy-civil / infrastructure project-controls resellers",
        "focus": "Resellers of project-controls/scheduling for heavy-civil and infrastructure.",
        "example_reseller_software": ["Bentley SYNCHRO", "Oracle Primavera P6", "Trimble ProjectSight"],
    },
    "fsm": {
        "name": "Field service management (FSM) resellers",
        "focus": "Resellers of field-service/mobile-workforce software.",
        "example_reseller_software": ["Salesforce Field Service", "Dynamics 365 Field Service", "ServiceNow FSM"],
    },
    "commissioning-handover": {
        "name": "Commissioning / building-handover / digital-closeout resellers",
        "focus": "Resellers of commissioning and closeout/handover software.",
        "example_reseller_software": ["CxAlloy", "Facility Grid", "Bluebeam"],
    },
    "construction-erp-accounting": {
        "name": "Construction ERP / accounting resellers",
        "focus": "Resellers of contractor back-office ERP/accounting software.",
        "example_reseller_software": ["Sage 300 CRE", "Viewpoint Vista", "Acumatica Construction", "Foundation"],
    },
    "analytics-bi": {
        "name": "Analytics / BI integrators",
        "focus": "BI/analytics integrators building construction dashboards and data pipelines.",
        "example_reseller_software": ["Power BI", "Tableau", "Snowflake"],
    },
    "trade-subcontractor": {
        "name": "Trade-contractor / subcontractor field-ops resellers",
        "focus": "Resellers serving specialty/trade contractors with field-ops software.",
        "example_reseller_software": ["Fieldwire", "Buildertrend", "Raken"],
    },
    "rugged-hardware": {
        "name": "Rugged hardware / field-workstation suppliers",
        "focus": "Suppliers of rugged tablets/workstations that bundle field software.",
        "example_reseller_software": ["Getac", "Panasonic Toughbook", "Zebra"],
    },
    "scheduling-estimating": {
        "name": "Project scheduling & estimating resellers",
        "focus": "Resellers of planning/scheduling and estimating software.",
        "example_reseller_software": ["Oracle Primavera P6", "Microsoft Project", "Sage Estimating"],
    },
    "datech-apac": {
        "name": "APAC construction-tech resellers (BCA / IMDA ecosystem)",
        "focus": "APAC ConTech resellers aligned to Singapore BCA/IMDA grant-approved solutions.",
        "example_reseller_software": ["BCA CORENET", "Autodesk Construction Cloud (APAC)", "local ConTech"],
    },

    # --- Real-time 3D / XR / digital twin (Unity) -------------------------- #
    "cad-dataprep-pixyz": {
        "name": "CAD / PLM / industrial 3D-visualization & data-prep resellers (Pixyz / Asset Transformer)",
        "focus": "CAD/PLM resellers whose industrial customers need CAD-to-real-time data prep.",
        "example_reseller_software": ["SOLIDWORKS", "Siemens NX", "CATIA", "PTC Creo"],
    },
    "xr-arvr": {
        "name": "XR / AR-VR hardware & immersive-systems integrators",
        "focus": "Integrators of AR/VR headsets and immersive enterprise systems.",
        "example_reseller_software": ["Meta Quest for Business", "Varjo", "HTC Vive", "Pico"],
    },
    "digital-twin-iot": {
        "name": "Digital twin / IoT / industrial simulation integrators",
        "focus": "Integrators of digital-twin/IoT platforms needing a real-time 3D layer.",
        "example_reseller_software": ["Siemens Teamcenter", "PTC ThingWorx", "AWS IoT TwinMaker", "NVIDIA Omniverse"],
    },
    "immersive-training": {
        "name": "Immersive training & simulation providers",
        "focus": "Providers of VR/AR training and simulation content.",
        "example_reseller_software": ["STRIVR", "Talespin", "PIXO VR", "Vuforia"],
    },
    "game-dev-tools": {
        "name": "Game-development tools & interactive-content resellers",
        "focus": "Resellers of engines, DCC and dev tools serving game/interactive studios.",
        "example_reseller_software": ["Perforce Helix Core", "Autodesk Maya", "3ds Max", "JetBrains Rider"],
    },
    "automotive-hmi": {
        "name": "Automotive HMI / embedded resellers",
        "focus": "Resellers/integrators of automotive HMI and embedded UI toolchains.",
        "example_reseller_software": ["Qt", "Elektrobit", "Rightware Kanzi", "BlackBerry QNX"],
    },
    "media-vfx-vp": {
        "name": "Media & entertainment / VFX / virtual-production resellers",
        "focus": "Resellers of DCC/VFX/virtual-production tools serving studios.",
        "example_reseller_software": ["Autodesk Maya", "3ds Max", "Foundry Nuke", "SideFX Houdini"],
    },
    "product-configurator": {
        "name": "3D product-configurator / e-commerce visualization agencies",
        "focus": "Agencies building interactive 3D configurators and commerce experiences.",
        "example_reseller_software": ["Threekit", "Zakeke", "Emersya", "Adobe Substance 3D"],
    },
    "gpu-parsec-msp": {
        "name": "GPU workstation / cloud-graphics / remote-visualization MSPs (Parsec)",
        "focus": "MSPs delivering GPU workstations, VDI and remote-3D streaming.",
        "example_reseller_software": ["NVIDIA RTX / vGPU", "AWS", "Microsoft Azure", "HP Anyware"],
    },
    "mobile-growth": {
        "name": "Mobile app growth / advertising / monetization partners (Unity Grow)",
        "focus": "Ad-tech/mobile-growth partners serving app publishers.",
        "example_reseller_software": ["AppLovin", "Google AdMob", "AppsFlyer", "ironSource"],
    },
}

# --------------------------------------------------------------------------- #
# Per-vendor verticals (slug, tier). Vendor keys match gtm.prompts.vendor_presets.
# --------------------------------------------------------------------------- #
VENDOR_VERTICALS: dict[str, list[tuple[str, str]]] = {
    "Trimble": [
        ("geospatial-survey", CORE),
        ("structural-steel-detailing", CORE),
        ("construction-erp-pm", CORE),
        ("archviz-rendering", CORE),
        ("cde-bim-coordination", CORE),
        ("mep-building-services", CORE),
        ("estimating-takeoff", CORE),
        ("interior-woodworking", CORE),
        ("field-machine-control", CORE),
        ("autodesk-aec-vars", SECONDARY),
        ("civil-infrastructure", SECONDARY),
        ("contech-management", SECONDARY),
        ("aec-it-msp", DEFER),
    ],
    "Bricsys": [
        ("autocad-alternative", CORE),
        ("mechanical-mcad", CORE),
        ("plant-process", CORE),
        ("civil-survey", CORE),
        ("reality-capture", CORE),
        ("mep-building-services", CORE),
        ("cad-app-developers", CORE),
        ("aec-bim-alternative", SECONDARY),
        ("cam-machining", SECONDARY),
        ("sheet-metal-nesting", SECONDARY),
        ("cad-interop", SECONDARY),
        ("gis-geospatial", SECONDARY),
        ("cafm-iwms", SECONDARY),
        ("ecad-electrical", SECONDARY),
        ("additive-manufacturing", DEFER),
        ("cae-simulation", DEFER),
        ("mes-digital-twin", DEFER),
    ],
    "DraftSight": [
        ("solidworks-vars", CORE),
        ("autocad-alternative", CORE),
        ("mechanical-mcad", CORE),
        ("broadline-it", CORE),
        ("pdm-plm", SECONDARY),
        ("aec-2d-cad", SECONDARY),
        ("ecad-electrical", SECONDARY),
        ("sheet-metal-nesting", SECONDARY),
        ("cafm-iwms", SECONDARY),
        ("plant-process", SECONDARY),
        ("education-academic", SECONDARY),
        ("additive-manufacturing", DEFER),
        ("cae-simulation", DEFER),
        ("technical-comms", DEFER),
    ],
    "Newforma": [
        ("autodesk-aec-vars", CORE),
        ("bim-coordination-clash", CORE),
        ("bluebeam-markup", CORE),
        ("acc-procore-integrators", CORE),
        ("m365-aec-it", CORE),
        ("construction-admin", CORE),
        ("aeco-msp", CORE),
        ("aeco-document-control", SECONDARY),
        ("construction-erp-pm", SECONDARY),
        ("design-authoring-addins", SECONDARY),
        ("bentley-infrastructure", DEFER),
        ("aec-elearning", DEFER),
        ("enterprise-crm", DEFER),
    ],
    "Novade": [
        ("contech-management", CORE),
        ("ehs-safety", CORE),
        ("quality-inspection", CORE),
        ("commissioning-handover", CORE),
        ("trade-subcontractor", CORE),
        ("datech-apac", CORE),
        ("acc-procore-integrators", SECONDARY),
        ("cmms-eam", SECONDARY),
        ("cde-bim-coordination", SECONDARY),
        ("field-punchlist", SECONDARY),
        ("cafm-iwms", SECONDARY),
        ("heavy-civil", SECONDARY),
        ("fsm", SECONDARY),
        ("construction-erp-accounting", SECONDARY),
        ("analytics-bi", SECONDARY),
        ("reality-capture", SECONDARY),
        ("rugged-hardware", SECONDARY),
        ("scheduling-estimating", DEFER),
    ],
    "Unity": [
        ("cad-dataprep-pixyz", CORE),
        ("xr-arvr", CORE),
        ("digital-twin-iot", CORE),
        ("immersive-training", CORE),
        ("game-dev-tools", CORE),
        ("aec-realtime-viz", CORE),
        ("automotive-hmi", CORE),
        ("product-configurator", CORE),
        ("gpu-parsec-msp", CORE),
        ("education-academic", CORE),
        ("mobile-growth", CORE),
        ("reality-capture", SECONDARY),
        ("gis-geospatial", SECONDARY),
        ("media-vfx-vp", DEFER),
    ],
}

# --------------------------------------------------------------------------- #
# Competitor exclusions — locked top-tier partners to exclude (they won't add a
# competing line). "*" means the vendor's own subsidiaries are always excluded.
# --------------------------------------------------------------------------- #
VENDOR_EXCLUSIONS: dict[str, dict[str, list[str]]] = {
    "Trimble": {"Autodesk": ["Gold", "Platinum", "Premier"], "Bentley": ["SELECT"], "Nemetschek": ["Platinum"]},
    "Bricsys": {"Autodesk": ["Gold", "Platinum", "Premier"]},
    "DraftSight": {"Autodesk": ["Gold", "Platinum"]},  # NOT Dassault/SOLIDWORKS (own family)
    "Newforma": {"Bentley ProjectWise": ["exclusive"], "Oracle Aconex": ["exclusive"]},
    "Novade": {"Fieldwire": ["exclusive"], "Dalux": ["exclusive"]},
    "Unity": {"Epic Unreal Engine": ["exclusive"]},
}


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Import-time validation — cheap O(n) integrity check.
# --------------------------------------------------------------------------- #
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


_validate()
