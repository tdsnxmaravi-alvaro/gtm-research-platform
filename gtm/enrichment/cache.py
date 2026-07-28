"""Cross-run contact cache — never re-fetch (or re-charge) a company already enriched.

Keyed by normalized domain. When a company's domain is in the cache, its contacts
are reused instead of calling Apollo/LARA again, saving credits across runs and
campaigns. The cache lives outside campaign folders so it is shared.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import EnrichedContact, CONTACT_COLS

DEFAULT_CACHE = Path(".gtm_cache") / "contacts.json"


def _norm_domain(domain: str) -> str:
    d = (domain or "").strip().lower()
    return d[4:] if d.startswith("www.") else d


class ContactCache:
    """Persistent domain -> contacts cache (shared across campaigns)."""

    def __init__(self, path: str | Path | None = None, enabled: bool = True):
        self.path = Path(path or DEFAULT_CACHE)
        self.enabled = enabled
        self.data: dict = {}
        if self.enabled and self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.data = {}

    def get(self, domain: str) -> list[EnrichedContact] | None:
        if not self.enabled:
            return None
        rec = self.data.get(_norm_domain(domain))
        if not rec:
            return None
        rows = rec.get("contacts") or []
        return [EnrichedContact(**{k: r.get(k, "") for k in CONTACT_COLS}) for r in rows]

    def put(self, domain: str, contacts: list[EnrichedContact]) -> None:
        if not self.enabled:
            return
        key = _norm_domain(domain)
        if not key:
            return
        self.data[key] = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "contacts": [c.to_row() for c in contacts],
        }
        self._save()

    def known_emails(self) -> set:
        """All emails already seen (any domain) — useful to avoid duplicates."""
        out = set()
        for rec in self.data.values():
            for c in rec.get("contacts") or []:
                e = (c.get("email") or "").strip().lower()
                if e:
                    out.add(e)
        return out

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
