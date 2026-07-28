"""Ingest — parse LLM research output and provided input lists into normalized rows.

- parse_results(text): robustly extract the fixed JSON schema {"results": [...]}
  from an LLM response (handles markdown fences / surrounding prose) and normalize
  each result to standard columns, including evidence-URL bookkeeping.
- load_provided_list(path): read a supplied company list (CSV) with normalized headers.
- write_rows_csv(rows, path): persist normalized rows.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

RESULT_COLUMNS = [
    "company", "website", "fit_summary", "score", "tier",
    "recommended_products", "notes",
    "evidence_urls", "evidence_count", "has_verified_url", "evidence",
]

# Header variants -> normalized name for provided input lists
_HEADER_MAP = {
    "company": "company", "company name": "company", "name": "company",
    "account": "company", "reseller": "company",
    "reseller name": "company", "resellername": "company", "partner name": "company",
    "website": "website", "url": "website", "domain": "website", "web": "website",
}


def _extract_json(text: str) -> dict | list | None:
    """Pull the outermost JSON object/array from a possibly-noisy LLM response."""
    fence = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", text or "", re.DOTALL)
    candidate = fence.group(1) if fence else None
    if not candidate:
        m = re.search(r"(\{.*\}|\[.*\])", text or "", re.DOTALL)
        candidate = m.group(1) if m else None
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def normalize_result(r: dict) -> dict:
    """Normalize one LLM result object to the standard result columns."""
    evidence = r.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = []
    urls = [
        str(e.get("url")).strip()
        for e in evidence
        if isinstance(e, dict) and e.get("url")
    ]
    rec = r.get("recommended_products") or []
    if isinstance(rec, str):
        rec = [rec]
    return {
        "company": str(r.get("company", "")).strip(),
        "website": str(r.get("website", "")).strip(),
        "fit_summary": str(r.get("fit_summary", "")).strip(),
        "score": r.get("score", ""),
        "tier": str(r.get("tier", "")).strip().upper(),
        "recommended_products": "; ".join(str(x) for x in rec),
        "notes": str(r.get("notes", "")).strip(),
        "evidence_urls": "; ".join(urls),
        "evidence_count": len(urls),
        "has_verified_url": bool(urls),
        "evidence": json.dumps(evidence, ensure_ascii=False),
    }


def parse_results(text: str) -> list[dict]:
    """Parse an LLM research response into a list of normalized result rows."""
    obj = _extract_json(text)
    if obj is None:
        return []
    results = obj.get("results") if isinstance(obj, dict) else obj
    if not isinstance(results, list):
        return []
    return [normalize_result(r) for r in results if isinstance(r, dict)]


def load_provided_list(path: str | Path) -> list[dict]:
    """Read a provided company list and normalize its headers.

    Supports CSV and Excel (.xlsx). The first row is treated as the header; the
    first sheet is used for Excel. Header variants are mapped to `company` /
    `website` via `_HEADER_MAP`.
    """
    path = Path(path)
    raw_rows = _read_xlsx(path) if path.suffix.lower() in (".xlsx", ".xlsm") else _read_csv(path)
    rows: list[dict] = []
    for raw in raw_rows:
        row: dict = {}
        for k, v in raw.items():
            key = _HEADER_MAP.get((k or "").strip().lower(), (k or "").strip().lower())
            row[key] = ("" if v is None else str(v)).strip()
        if row.get("company"):
            rows.append(row)
    return rows


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _read_xlsx(path: Path) -> list[dict]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header = [str(c).strip() if c is not None else "" for c in next(rows_iter)]
    except StopIteration:
        wb.close()
        return []
    out: list[dict] = []
    for values in rows_iter:
        if values is None or all(v is None for v in values):
            continue
        out.append({header[i]: values[i] for i in range(min(len(header), len(values)))})
    wb.close()
    return out


def write_rows_csv(rows: list[dict], path: str | Path, columns: list[str] | None = None) -> None:
    """Write normalized rows to CSV (utf-8-sig for Excel)."""
    if not rows:
        columns = columns or RESULT_COLUMNS
    else:
        columns = columns or list({k for r in rows for k in r}) or RESULT_COLUMNS
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
