"""Flag which companies are already Datech resellers (net-new vs existing).

Ported from the verticals project's ``match_datech.py``. Given a reseller list
(a CSV export from TD SYNNEX invoicing with a ``Reseller`` column — region-
agnostic: any regional export works), match discovered companies by name using
exact / brand-token / high-threshold-fuzzy strategies. Flags only, never excludes.
"""

from __future__ import annotations

import csv
import re
from difflib import SequenceMatcher
from pathlib import Path

# Words too generic to identify a brand on their own.
_STOP_WORDS = {
    "TECHNOLOGIES", "TECHNOLOGY", "TECH", "SYSTEMS", "SOLUTIONS", "SERVICES",
    "CANADA", "USA", "INTERNATIONAL", "INTL", "CONSULTING",
    "ENTERPRISES", "PARTNERS", "ASSOCIATES", "RESOURCES", "COMMUNICATIONS",
    "COMPUTER", "DIGITAL", "GLOBAL", "NETWORK", "NETWORKS", "DATA",
    "DESIGN", "ENGINEERING", "SOFTWARE", "HARDWARE", "ELECTRONICS",
    "NORTH", "SOUTH", "EAST", "WEST", "AMERICA", "AMERICAN",
    "THE", "AND", "OF", "FOR", "BY",
}


def load_datech_names(csv_path: str | Path, column: str = "Reseller") -> list[str]:
    """Load reseller names from a Datech invoicing CSV export."""
    path = Path(csv_path)
    names: set[str] = set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        col = column if column in (reader.fieldnames or []) else (reader.fieldnames or [""])[0]
        for row in reader:
            name = (row.get(col) or "").strip()
            if name and name.upper() != "NULL":
                names.add(name)
    return sorted(names)


def normalize_for_match(name: str) -> str:
    n = (name or "").upper()
    n = re.sub(r"\b(INC|LLC|LTD|CORP|CO|LP|ULC|INCORPORATED|CORPORATION)\b\.?", "", n)
    n = re.sub(r"\bDBA\b.*", "", n)          # drop "doing business as" clauses
    n = re.sub(r"\(.*?\)", "", n)            # drop parentheticals
    n = re.sub(r"[^A-Z0-9\s]", "", n)
    return re.sub(r"\s+", " ", n).strip()


def brand_tokens(normalized: str) -> set[str]:
    return set(normalized.split()) - _STOP_WORDS


class DatechIndex:
    """Pre-normalized Datech names for repeated matching."""

    def __init__(self, names: list[str]):
        self.normalized = {n: normalize_for_match(n) for n in names}
        self.tokens = {n: brand_tokens(v) for n, v in self.normalized.items()}

    def find(self, company: str) -> str | None:
        v_norm = normalize_for_match(company)
        if not v_norm:
            return None
        v_tokens = brand_tokens(v_norm)

        for original, d_norm in self.normalized.items():
            if v_norm == d_norm:                       # 1. exact normalized
                return original

        # 2. brand-token match — require >=2 tokens so names that reduce to a single
        # generic token (e.g. "Applied Software" -> {APPLIED}) don't cross-match.
        if len(v_tokens) >= 2:
            for original, d_tokens in self.tokens.items():
                if len(d_tokens) < 2:
                    continue
                if v_tokens == d_tokens:               # 2a. same brand tokens
                    return original
                smaller, larger = ((v_tokens, d_tokens) if len(v_tokens) <= len(d_tokens)
                                   else (d_tokens, v_tokens))
                if smaller < larger and len(smaller) >= 2 and all(len(t) >= 2 for t in smaller):
                    return original                    # 2b. proper 2+ token subset

        if len(v_norm.split()) >= 3:                   # 3. high-threshold fuzzy (long names)
            best_score, best_match = 0.0, None
            for original, d_norm in self.normalized.items():
                if len(d_norm.split()) < 3 or abs(len(v_norm) - len(d_norm)) > 8:
                    continue
                score = SequenceMatcher(None, v_norm, d_norm).ratio()
                if score > best_score:
                    best_score, best_match = score, original
            if best_score >= 0.90:
                return best_match
        return None


def match_companies(companies: list[str], datech_names: list[str]) -> dict[str, str]:
    """Return {company: matched_datech_name} for companies already in the Datech list."""
    index = DatechIndex(datech_names)
    out: dict[str, str] = {}
    for company in companies:
        match = index.find(company)
        if match:
            out[company] = match
    return out
