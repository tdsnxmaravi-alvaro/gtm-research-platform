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
    "load_campaign",
]
