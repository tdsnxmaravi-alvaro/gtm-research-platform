"""Prompt templates for the 5 (target_type x mode) research families.

Skeletons with {{PLACEHOLDERS}} filled by builder.py. The dynamic blocks
(fit criteria, evidence rules, scoring, output schema) are composed in Python so
all templates stay consistent and DRY.
"""

# --------------------------------------------------------------------------- #
# Shared blocks (rendered by the builder and injected as placeholders)
# --------------------------------------------------------------------------- #
EVIDENCE_RULES = """\
EVIDENCE & ANTI-HALLUCINATION RULES (STRICT):
- Use web search. Cite a clickable source URL for EVERY factual claim.
- NEVER invent companies, contacts, projects, or facts. If unsure, say so.
- If a claim cannot be backed by a verified URL, mark it "UNVERIFIED" and do not score on it.
- VALIDATION GATE: with ZERO verified source URLs, the company CANNOT exceed tier {tier_cap},
  no matter how strong the inferential signals look.
- Job boards, press releases, official pages and reputable directories are valid URLs."""

OUTPUT_SCHEMA = """\
OUTPUT — return STRICT JSON only (no prose, no markdown fences), one object per company:
{"results": [
  {
    "company": "...",
    "website": "...",
    "employees": "approx. headcount or size band if verifiable (e.g. '51-200'), else empty",
    "software_resold": "key software brands/products they sell or resell, comma-separated, else empty",
    "independence": "Independent | Subsidiary | Acquired | empty (ownership status, only if verifiable)",
    "fit_summary": "1-3 sentences on why it does / does not fit",
    "dimension_scores": [
      {"name": "<exact dimension name>", "points": <int>, "max": <int>,
       "rationale": "which band and why", "evidence_url": "https://..."}
    ],
    "recommended_products": ["..."],
    "notes": "acquisitions, risks, caveats, or UNVERIFIED flags"
  }
]}
Score EACH dimension listed under SCORING against its point-band anchors, using the
EXACT dimension name and its max. Do NOT output an overall score — it is computed
deterministically as the sum of dimension points. Any dimension scored above its
lowest band SHOULD carry an evidence_url; without verifiable evidence, keep it in
the lowest band."""


# --------------------------------------------------------------------------- #
# Templates keyed by CampaignConfig.prompt_template_key()
# --------------------------------------------------------------------------- #
RESELLER_PROVIDED_FIT = """\
You are a senior channel-development research analyst for TD SYNNEX.
Qualify whether each company below is a strong RESELLER partner for {product_name} —
i.e., could they SELL/service this product to their customers?
Work in each company's OWN country: the country is given per company in the list below
(use it for localization and local-presence checks). Campaign default country, used only
as a fallback when a row has none: {country}.

PRODUCT: {product_name} — {value_prop}

FIT CRITERIA (fit to SELL the product):
{fit_criteria}

{evidence_rules}

SCORING:
{scoring}

COMPANIES TO QUALIFY:
{company_input}

{output_schema}"""

ACCOUNT_PROVIDED_FIT = """\
You are a senior demand-generation research analyst for TD SYNNEX.
Qualify whether each ACCOUNT / end-user company below is a strong prospect to BUY/USE
{product_name} — based on active demand signals, not channel capability.
Work in each company's OWN country: the country is given per company in the list below
(use it for localization and local-market checks). Campaign default country, used only
as a fallback when a row has none: {country}.

PRODUCT: {product_name} — {value_prop}

FIT CRITERIA (fit to BUY/USE the product — look for demand triggers such as active
projects, hiring, M&A/consolidation, expansion, or the specific pains this product solves):
{fit_criteria}

{evidence_rules}

SCORING:
{scoring}

ACCOUNTS TO QUALIFY:
{company_input}

{output_schema}"""

RESELLER_DISCOVER_BROAD = """\
You are a senior channel-strategy analyst for TD SYNNEX.
Find independent RESELLERS operating in {country} that could add {product_name} to their
portfolio — companies that sell/service related software to end customers and fit to SELL this product.

PRODUCT: {product_name} — {value_prop}

FIT CRITERIA:
{fit_criteria}

{evidence_rules}

SCORING:
{scoring}

{output_schema}"""

RESELLER_DISCOVER_VERTICAL = """\
You are a senior channel-strategy analyst for TD SYNNEX.
Find independent RESELLERS in the {vertical_name} vertical operating in {country} that could
add {product_name} to their portfolio (fit to SELL this product to their customers).

PRODUCT: {product_name} — {value_prop}

FIT CRITERIA:
{fit_criteria}

{evidence_rules}

SCORING:
{scoring}

{output_schema}"""

ACCOUNT_DISCOVER_BROAD = """\
You are a senior demand-generation analyst for TD SYNNEX.
Find end-user companies (ACCOUNTS) in {country} with active demand signals that make them
strong prospects to BUY/USE {product_name}.

PRODUCT: {product_name} — {value_prop}

FIT CRITERIA (demand triggers):
{fit_criteria}

{evidence_rules}

SCORING:
{scoring}

{output_schema}"""


TEMPLATES = {
    "resellers_provided_fit": RESELLER_PROVIDED_FIT,
    "accounts_provided_fit": ACCOUNT_PROVIDED_FIT,
    "resellers_discover_broad": RESELLER_DISCOVER_BROAD,
    "reseller_discover_vertical": RESELLER_DISCOVER_VERTICAL,
    "accounts_discover_broad": ACCOUNT_DISCOVER_BROAD,
}
