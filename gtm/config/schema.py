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


class ScoringDimension(BaseModel):
    name: str
    max_points: int = 10
    weight: float = 1.0
    description: str = ""


class Scoring(BaseModel):
    dimensions: list[ScoringDimension] = Field(default_factory=list)
    # Tier lower-bound thresholds (score >= value). Ordered best -> worst.
    tier_thresholds: dict[str, int] = Field(
        default_factory=lambda: {"A": 85, "B": 70, "C": 50, "D": 0}
    )
    # URL gate: with ZERO verified source URLs, the account cannot exceed this tier.
    unverified_tier_cap: str = "C"


class Enrichment(BaseModel):
    apollo: bool = False
    want: EnrichWant = EnrichWant.emails
    max_contacts: int = 3
    provider: EnrichProvider = EnrichProvider.lara
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
    assistant_id_env: str | None = None


class Outreach(BaseModel):
    enabled: bool = False
    language: str | None = None          # default: campaign language
    template_eml: str | None = None       # path to a sample .eml (branded template)
    agent_assistant_id_env: str | None = None


# --------------------------------------------------------------------------- #
# Root campaign config
# --------------------------------------------------------------------------- #
class CampaignConfig(BaseModel):
    name: str
    target_type: TargetType
    mode: Mode
    country: str
    language: str | None = None           # default derived from country

    products: list[Product] = Field(min_length=1)
    verticals: list[Vertical] = Field(default_factory=list)
    provided_list_path: str | None = None

    scoring: Scoring = Field(default_factory=Scoring)
    enrichment: Enrichment = Field(default_factory=Enrichment)
    llm_providers: list[LLMProvider] = Field(default_factory=list)
    research_provider: str = "lara"       # provider `name` used for research
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

        # Derive language defaults from country
        default_lang = COUNTRY_LANGUAGE.get(self.country.strip().lower(), "en")
        if self.language is None:
            self.language = default_lang
        if self.outreach.language is None:
            self.outreach.language = self.language
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
