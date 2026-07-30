"""Cross-run research cache — reuse a company's scored analysis for the same vendor.

Keyed by (vendor, target_type, product, domain). When a company was already
researched for the same vendor/product in a previous run or campaign, its scored
row is reused instead of calling the LLM again — saving tokens and time. Lives
outside campaign folders (shared), like the contact cache.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..enrichment.domains import extract_domain

DEFAULT_CACHE = Path(".gtm_cache") / "research.json"


def _domain_or_name(row: dict) -> str:
    return (extract_domain(row.get("website") or "")
            or (row.get("company") or "").strip().lower())


class ResearchCache:
    """Persistent (vendor, target, product, domain) -> scored row cache."""

    def __init__(self, path: str | Path | None = None, enabled: bool = True):
        self.path = Path(path or DEFAULT_CACHE)
        self.enabled = enabled
        self.data: dict = {}
        if self.enabled and self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.data = {}

    @staticmethod
    def key(vendor: str, target_type: str, product: str, domain: str) -> str:
        return f"{(vendor or '').strip().lower()}|{target_type}|{(product or '').strip().lower()}|{domain}"

    def get(self, key: str) -> dict | None:
        if not self.enabled:
            return None
        rec = self.data.get(key)
        return dict(rec["row"]) if rec else None

    def put(self, key: str, row: dict) -> None:
        if not self.enabled or not key:
            return
        self.data[key] = {"cached_at": datetime.now(timezone.utc).isoformat(),
                          "row": dict(row)}
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                             encoding="utf-8")
