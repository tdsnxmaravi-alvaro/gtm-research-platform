"""Prompt building for the research stage."""

from .builder import build_prompt, format_companies
from .vendor_presets import preset_for, enrich_config_dict, VENDOR_PRESETS
from .vertical_presets import (
    VERTICAL_PRESETS, VENDOR_VERTICALS, VENDOR_EXCLUSIONS,
    verticals_for, vertical_preset, exclusions_for, exclusion_note,
    discover_verticals, CORE, SECONDARY, DEFER,
)
from . import templates

__all__ = ["build_prompt", "format_companies", "templates",
           "preset_for", "enrich_config_dict", "VENDOR_PRESETS",
           "VERTICAL_PRESETS", "VENDOR_VERTICALS", "VENDOR_EXCLUSIONS",
           "verticals_for", "vertical_preset", "exclusions_for", "exclusion_note",
           "discover_verticals", "CORE", "SECONDARY", "DEFER"]
