"""
Campaign configuration schema for the GTM Research Platform.

A single campaign config (YAML) drives an entire project. This module defines the
Pydantic models plus the *conditional* validation that enforces the valid
combinations of (target_type, mode, verticals):

    Golden rule: verticals ONLY exist in `discover` mode (they scope the search).
      - `provided` never has verticals.
      - `accounts` never have verticals.

Valid combinations:
    resellers + discover + verticals(optional)  -> OK
    resellers + provided (no verticals)         -> OK
    accounts  + provided (no verticals)          -> OK
    accounts  + discover-broad (no verticals)    -> OK
    accounts  + discover per-vertical            -> INVALID
    any       + provided + verticals             -> INVALID
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class TargetType(str, Enum):
    resellers = "resellers"   # does the company fit to SELL the product (channel)
    accounts = "accounts"     # does the end-user fit to BUY/USE the product (demand)


class Mode(str, Enum):
    discover = "discover"     # find companies that fit
    provided = "provided"     # qualify a supplied list


class EnrichWant(str, Enum):
    none = "none"
    emails = "emails"
    emails_phones = "emails+phones"


class ProviderType(str, Enum):
    lara = "lara"
    azure_openai = "azure_openai"
    azure_foundry = "azure_foundry"
    manual = "manual"


class EnrichProvider(str, Enum):
    apollo = "apollo"
    lara = "lara"


# Minimal country -> default language (locale) map; extend as needed.
COUNTRY_LANGUAGE = {
    "spain": "es",
    "españa": "es",
    "mexico": "es",
    "méxico": "es",
    "usa": "en",
    "united states": "en",
    "canada": "en",
    "uk": "en",
    "united kingdom": "en",
    "france": "fr",
    "germany": "de",
    "italy": "it",
    "brazil": "pt",
    "portugal": "pt",
}

# Country -> Apollo `organization_locations` / `person_locations` label(s).
# Used by the Apollo enrichment path so location is derived from the campaign
# country instead of being hard-coded. Falls back to the raw country string.
COUNTRY_APOLLO_LOCATIONS = {
    "spain": ["Spain"],
    "españa": ["Spain"],
    "mexico": ["Mexico"],
    "méxico": ["Mexico"],
    "usa": ["United States"],
    "united states": ["United States"],
    "canada": ["Canada"],
    "uk": ["United Kingdom"],
    "united kingdom": ["United Kingdom"],
    "france": ["France"],
    "germany": ["Germany"],
    "italy": ["Italy"],
    "brazil": ["Brazil"],
    "portugal": ["Portugal"],
}


def apollo_locations_for(country: str) -> list[str]:
    """Return Apollo location labels for a campaign country (best-effort)."""
    key = (country or "").strip().lower()
    return COUNTRY_APOLLO_LOCATIONS.get(key, [country.strip()] if country else [])


# Curated TD SYNNEX / Datech go-to-market countries, grouped by region. Used by
# the discover wizard's country selector; discover runs one research pass per
# selected country per vertical.
DATECH_COUNTRIES: dict[str, list[str]] = {
    "North America": ["United States", "Canada"],
    "Caribbean & Central America": [
        "Guatemala", "El Salvador", "Honduras", "Costa Rica", "Panama",
        "Dominican Republic", "Jamaica", "Trinidad & Tobago", "Barbados", "Puerto Rico",
    ],
    "EMEA": [
        "United Kingdom", "Ireland", "France", "Germany", "Netherlands", "Belgium",
        "Luxembourg", "Spain", "Portugal", "Italy", "Switzerland", "Austria", "Poland",
        "Czech Republic", "Slovakia", "Hungary", "Romania", "Bulgaria", "Greece",
        "Sweden", "Norway", "Denmark", "Finland", "South Africa",
    ],
    "APJ": [
        "Brunei", "India", "Indonesia", "Malaysia", "Singapore", "Thailand",
        "Vietnam", "Cambodia", "Hong Kong", "Japan",
    ],
}


def language_for_country(country: str) -> str | None:
    """Map a country to its default language, or None if unknown."""
    return COUNTRY_LANGUAGE.get((country or "").strip().lower())


# --------------------------------------------------------------------------- #
# Sub-models
# --------------------------------------------------------------------------- #
class Product(BaseModel):
    name: str
    value_prop: str = ""
    # Optional explicit prompt override; else built from template + fit_criteria.
    search_prompt: str | None = None
    fit_criteria: list[str] = Field(default_factory=list)
    evidence_required: bool = True


class Vertical(BaseModel):
    name: str
    slug: str
    prompt: str | None = None
    dimensions: list[ScoringDimension] = Field(default_factory=list)
    # Discover-mode context (from gtm.prompts.vertical_presets): why this reseller
    # pool fits the vendor, and the software brands whose resellers we recruit.
    focus: str = ""
    example_software: list[str] = Field(default_factory=list)


class ScoringDimension(BaseModel):
    name: str
    max_points: int = 10
    weight: float = 1.0
    description: str = ""
    # Point-band anchors (rubric) that pin the model to concrete criteria and cut
    # run-to-run variance, e.g. ["11-15: resells design software with services",
    # "6-10: generic IT software only", "0-5: no software resale / box-mover"].
    anchors: list[str] = Field(default_factory=list)


class Scoring(BaseModel):
    dimensions: list[ScoringDimension] = Field(default_factory=list)
    # Prepend the reusable universal (vendor/vertical-agnostic) dimensions for the
    # campaign's target_type, then the campaign adds its specific dimensions.
    use_universal: bool = False
    # Tier lower-bound thresholds (score >= value). Ordered best -> worst.
    tier_thresholds: dict[str, int] = Field(
        default_factory=lambda: {"A": 85, "B": 70, "C": 50, "D": 0}
    )
    # URL gate: with ZERO verified source URLs, the account cannot exceed this tier.
    unverified_tier_cap: str = "C"
    # Discover-mode gates (safety nets on top of the prompt's exclusions):
    # a competitor-locked partner cannot exceed this tier.
    excluded_partner_tier_cap: str = "D"
    # a captive/subsidiary (non-independent) reseller cannot exceed this tier.
    captive_tier_cap: str = "C"

    def total_max_points(self) -> int:
        return sum(d.max_points for d in self.dimensions)


class Enrichment(BaseModel):
    apollo: bool = False
    want: EnrichWant = EnrichWant.emails
    max_contacts: int = 3
    provider: EnrichProvider = EnrichProvider.lara
    # Skip contact enrichment for companies already in the Datech channel (they're
    # existing partners) to save Apollo credits; validate later if worth enriching.
    skip_datech_matches: bool = True
    # Credit-estimate inputs (Apollo). Observed ~8 credits per phone reveal.
    credits_per_email: int = 1
    credits_per_phone: int = 8
    # Apollo people-search targeting (country-agnostic; locations derived from the
    # campaign country when left empty). Seniorities/titles pick decision-makers.
    seniorities: list[str] = Field(
        default_factory=lambda: [
            "owner", "founder", "c_suite", "vp", "head", "director", "manager",
        ]
    )
    titles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)

    def estimate_credits(self, num_companies: int) -> int:
        """Rough upfront Apollo credit estimate for a run."""
        if not self.apollo:
            return 0
        per_contact = self.credits_per_email
        if self.want == EnrichWant.emails_phones:
            per_contact += self.credits_per_phone
        return num_companies * self.max_contacts * per_contact


class LLMProvider(BaseModel):
    name: str
    type: ProviderType
    web_search: bool = False
    model: str | None = None
    # Secrets are referenced by ENV VAR NAME, never inlined.
    api_key_env: str | None = None
    endpoint_env: str | None = None
    endpoint_url: str | None = None       # inline endpoint (not a secret)
    assistant_id_env: str | None = None


class Outreach(BaseModel):
    enabled: bool = False
    language: str | None = None          # default: campaign language
    template_eml: str | None = None       # path to a sample .eml (branded template)
    logo_path: str | None = None          # path to a logo image (top banner in the frame)
    agent_assistant_id_env: str | None = None
    sender_name: str = ""                 # BDR name for the signature / From
    sender_email: str = ""               # BDR email for the From header
    min_tier: str = "B"                   # only draft outreach for tiers >= this
    subject: str | None = None            # optional subject override/template


# --------------------------------------------------------------------------- #
# Root campaign config
# --------------------------------------------------------------------------- #
class CampaignConfig(BaseModel):
    name: str
    target_type: TargetType
    mode: Mode
    country: str = ""
    vendor: str = ""                       # the vendor being sold (e.g. "Trimble")
    # Discover multi-country: run one research pass per country per vertical. When
    # empty, the single `country` is used. `country` also stays the language anchor.
    countries: list[str] = Field(default_factory=list)
    language: str | None = None           # default derived from country

    products: list[Product] = Field(min_length=1)
    verticals: list[Vertical] = Field(default_factory=list)
    provided_list_path: str | None = None
    # Optional CSV of existing Datech resellers (invoicing export, "Reseller"
    # column). When set, the master flags companies already in the Datech channel.
    datech_reseller_list: str | None = None
    # Raw-header (lowercased) -> canonical field ("company"/"website"/"country").
    # Set by the wizard's upload + column-mapping step; applied when loading the list.
    provided_column_overrides: dict[str, str] = Field(default_factory=dict)
    # Cap how many companies from the provided list to process (0 = all).
    process_limit: int = 0
    # Reuse a company's scored analysis for the same vendor/product across runs and
    # campaigns (saves LLM tokens). Disable to force fresh research.
    research_cache: bool = True
    # Research jobs to run concurrently (provided-mode batches and discover-mode
    # country×product×vertical keys). >1 sends parallel LLM requests so a large
    # list finishes far faster; keep modest to respect provider rate limits.
    research_concurrency: int = 3
    # Extra attempts (after the first) for a provider call that errors transiently,
    # so one flaky batch doesn't silently drop an ensemble member.
    research_retries: int = 2

    scoring: Scoring = Field(default_factory=Scoring)
    enrichment: Enrichment = Field(default_factory=Enrichment)
    llm_providers: list[LLMProvider] = Field(default_factory=list)
    research_provider: str = "lara"       # provider `name` used for research
    # Optional ensemble: run research across MULTIPLE providers and average the
    # per-dimension scores (diversifies models + reduces variance). When set, it
    # takes precedence over `research_provider`.
    research_providers: list[str] = Field(default_factory=list)
    outreach: Outreach = Field(default_factory=Outreach)

    # ----------------------------------------------------------------------- #
    @model_validator(mode="after")
    def _apply_and_validate(self) -> "CampaignConfig":
        has_verticals = len(self.verticals) > 0

        # Golden rule: verticals only in discover
        if has_verticals and self.mode != Mode.discover:
            raise ValueError(
                "Invalid combination: verticals are only allowed in 'discover' mode "
                "('provided' works from a supplied list and has no verticals)."
            )
        # accounts never have verticals
        if has_verticals and self.target_type == TargetType.accounts:
            raise ValueError(
                "Invalid combination: 'accounts' (end-users) never have verticals."
            )
        # provided needs a list
        if self.mode == Mode.provided and not self.provided_list_path:
            raise ValueError("mode 'provided' requires 'provided_list_path'.")

        # research provider must exist in the declared providers (if any declared)
        if self.llm_providers:
            names = {p.name for p in self.llm_providers}
            if self.research_provider not in names:
                raise ValueError(
                    f"research_provider '{self.research_provider}' is not in llm_providers {sorted(names)}."
                )
            missing = [n for n in self.research_providers if n not in names]
            if missing:
                raise ValueError(
                    f"research_providers {missing} not in llm_providers {sorted(names)}."
                )

        # Derive language defaults from country. Multi-country discover: anchor the
        # campaign country/language to the first selected country when only
        # `countries` was provided.
        if not self.country.strip() and self.countries:
            self.country = self.countries[0]
        default_lang = COUNTRY_LANGUAGE.get(self.country.strip().lower(), "en")
        if self.language is None:
            self.language = default_lang
        # NOTE: do NOT auto-fill outreach.language — leaving it None means "auto",
        # so outreach localizes per each company's own country (falling back to the
        # campaign language). An explicit outreach.language (user choice) still wins.

        # Prepend reusable universal scoring dimensions when requested.
        if self.scoring.use_universal:
            from ..scoring.library import universal_dimensions
            existing = {d.name for d in self.scoring.dimensions}
            universal = [
                ScoringDimension(**d)
                for d in universal_dimensions(self.target_type.value)
                if d["name"] not in existing
            ]
            self.scoring.dimensions = universal + self.scoring.dimensions
        return self

    # ----------------------------------------------------------------------- #
    def prompt_template_key(self) -> str:
        """Which prompt-builder template family applies to this campaign."""
        if self.mode == Mode.provided:
            return f"{self.target_type.value}_provided_fit"
        if self.target_type == TargetType.resellers and self.verticals:
            return "reseller_discover_vertical"
        return f"{self.target_type.value}_discover_broad"


# Resolve forward references (Vertical -> ScoringDimension defined below it)
Vertical.model_rebuild()
