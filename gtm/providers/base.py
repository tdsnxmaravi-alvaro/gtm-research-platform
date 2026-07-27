"""LLM provider abstraction.

Every provider takes a built prompt and returns text + extracted source URLs, so
the rest of the pipeline is provider-agnostic. Web-search-capable providers
(LARA; Azure only if the deployment supports grounding) power evidence-linked
research; others are fine for deterministic tasks.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

_URL_RE = re.compile(r"https?://[^\s\"'<>\]\)]+")


def extract_urls(text: str) -> list[str]:
    """Return de-duplicated source URLs found in a text blob (order preserved)."""
    seen: list[str] = []
    for url in _URL_RE.findall(text or ""):
        cleaned = url.rstrip(".,;)")
        if cleaned not in seen:
            seen.append(cleaned)
    return seen


@dataclass
class ProviderResponse:
    text: str
    sources: list[str] = field(default_factory=list)
    raw: dict | None = None


class BaseProvider(ABC):
    """Common interface: build the prompt elsewhere, send it here."""

    name: str = "base"
    web_search: bool = False

    @abstractmethod
    def send(self, prompt: str, web_search: bool | None = None) -> ProviderResponse:
        """Send a prompt and return text + source URLs."""
        raise NotImplementedError
