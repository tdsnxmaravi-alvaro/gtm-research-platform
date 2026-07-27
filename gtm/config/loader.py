"""Load and validate a campaign config from YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

from .schema import CampaignConfig


def load_campaign(path: str | Path) -> CampaignConfig:
    """Load a campaign YAML file and return a validated CampaignConfig."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return CampaignConfig.model_validate(data)
