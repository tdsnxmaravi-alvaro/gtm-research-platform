"""Org / channel display names for prompts and outreach copy.

Override with ``GTM_ORG_NAME`` / ``GTM_CHANNEL_NAME`` or campaign config fields
``org_name`` / ``channel_name``. Defaults keep the current TD SYNNEX / Datech branding.
"""

from __future__ import annotations

import os

DEFAULT_ORG_NAME = "TD SYNNEX"
DEFAULT_CHANNEL_NAME = "Datech"


def org_name(config=None) -> str:
    if config is not None:
        val = str(getattr(config, "org_name", "") or "").strip()
        if val:
            return val
    return (os.getenv("GTM_ORG_NAME") or DEFAULT_ORG_NAME).strip()


def channel_name(config=None) -> str:
    if config is not None:
        val = str(getattr(config, "channel_name", "") or "").strip()
        if val:
            return val
    return (os.getenv("GTM_CHANNEL_NAME") or DEFAULT_CHANNEL_NAME).strip()
