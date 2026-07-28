"""Campaign configuration: models, validation, and YAML loader."""

from .schema import (
    CampaignConfig,
    TargetType,
    Mode,
    EnrichWant,
    EnrichProvider,
    ProviderType,
    Product,
    Vertical,
    ScoringDimension,
    Scoring,
    Enrichment,
    LLMProvider,
    Outreach,
    apollo_locations_for,
    language_for_country,
)
from .loader import load_campaign

__all__ = [
    "CampaignConfig",
    "TargetType",
    "Mode",
    "EnrichWant",
    "EnrichProvider",
    "ProviderType",
    "Product",
    "Vertical",
    "ScoringDimension",
    "Scoring",
    "Enrichment",
    "LLMProvider",
    "Outreach",
    "apollo_locations_for",
    "language_for_country",
    "load_campaign",
]
