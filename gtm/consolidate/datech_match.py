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

# Bundled real Datech reseller export (FY22, AMER/APAC/EMEA). Used as the default
# when a campaign doesn't set its own datech_reseller_list.
DEFAULT_DATECH_CSV = Path(__file__).resolve().parents[2] / "data" / "datech" / "InvoicingFY22.csv"

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
    return [r["name"] for r in load_datech_records(csv_path, name_col=column)]


def load_datech_records(csv_path: str | Path, name_col: str = "Reseller") -> list[dict]:
    """Load Datech reseller rows (name + geo/region/country/csn when present).

    Dedupes by (name, country, csn). Skips empty / literal 'NULL' reseller names.
    """
    path = Path(csv_path)
    out: list[dict] = []
    seen: set[tuple] = set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        ncol = name_col if name_col in fields else (fields[0] if fields else "")

        def g(row: dict, *cands: str) -> str:
            for c in cands:
                if (row.get(c) or "").strip():
                    return row[c].strip()
            return ""

        for row in reader:
            name = (row.get(ncol) or "").strip()
            if not name or name.upper() == "NULL":
                continue
            rec = {
                "name": name,
                "geo": g(row, "Geo Area"),
                "region": g(row, "Region"),
                "country": g(row, "Country"),
                "csn": g(row, "Reseller CSN"),
            }
            key = (name, rec["country"], rec["csn"])
            if key not in seen:
                seen.add(key)
                out.append(rec)
    return out


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
    """Pre-normalized Datech names for repeated matching.

    Pass `records` (from load_datech_records) to enable country-aware matching via
    ``match``; otherwise pass a plain name list for name-only ``find``.
    """

    def __init__(self, names: list[str], records: list[dict] | None = None):
        self.by_name: dict[str, list[dict]] = {}
        if records is not None:
            for r in records:
                self.by_name.setdefault(r["name"], []).append(r)
            names = sorted(self.by_name)
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

    def match(self, company: str, country: str | None = None) -> dict | None:
        """Return the matched Datech record (country-aware) or None.

        Result: {name, geo, region, country, csn, same_country}. When `country` is
        given and the matched partner has an entry in that country, that entry is
        chosen and same_country=True; else same_country=False (matched in another
        market). Falls back to name-only when the index has no records.
        """
        name = self.find(company)
        if not name:
            return None
        recs = self.by_name.get(name)
        if not recs:
            return {"name": name, "geo": "", "region": "", "country": "",
                    "csn": "", "same_country": None}
        chosen, same = recs[0], None
        if country:
            c = country.strip().lower()
            hit = next((r for r in recs if r["country"].strip().lower() == c), None)
            chosen, same = (hit, True) if hit else (recs[0], False)
        return {**chosen, "same_country": same}


def match_companies(companies: list[str], datech_names: list[str]) -> dict[str, str]:
    """Return {company: matched_datech_name} for companies already in the Datech list."""
    index = DatechIndex(datech_names)
    out: dict[str, str] = {}
    for company in companies:
        match = index.find(company)
        if match:
            out[company] = match
    return out
