"""Consolidate research results + enriched contacts into a master list.

One row per contact (or one per company when no contacts), carrying the company's
tier/score/evidence alongside the contact's email/phone. Sorted by tier then score,
deduplicated by normalized company name. Exports CSV and XLSX for the BDM.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from ..config.schema import CampaignConfig

MASTER_COLS = [
    "tier", "score", "company", "website", "country",
    "contact_name", "title", "email", "email_status",
    "direct_phone", "corporate_phone", "linkedin",
    "vendor", "recommended_products", "fit_summary", "evidence_urls",
]

_TIER_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "": 9}


def normalize_name(name: str) -> str:
    """Normalize a company name for deduplication."""
    n = (name or "").upper().strip()
    n = re.sub(r"\(.*?\)", "", n)
    for suf in (" INC.", " INC", " LLC", " LTD.", " LTD", " CORP.", " CORP",
                " CO.", " CO", " L.P.", " LP", " LIMITED", " PTE",
                " S.L.U.", " S.L.", " SL", " S.A.", " SA", " SLU", " LDA"):
        if n.endswith(suf):
            n = n[:-len(suf)]
    n = re.sub(r"[^A-Z0-9 ]", "", n)
    return re.sub(r"\s+", " ", n).strip()


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_master(config: CampaignConfig, out_dir: str | Path | None = None,
                 min_tier: str | None = None) -> list[dict]:
    """Join results.csv + contacts.csv into a master list. Returns master rows."""
    out = Path(out_dir or (Path("campaigns") / config.name))
    results = _read_csv(out / "results.csv")
    contacts = _read_csv(out / "contacts.csv")

    tier_cap = _TIER_ORDER.get((min_tier or "").upper(), 9)

    # Best result row per normalized company (keep highest score).
    best: dict[str, dict] = {}
    for r in results:
        key = normalize_name(r.get("company", ""))
        if not key:
            continue
        prev = best.get(key)
        if prev is None or _score(r) > _score(prev):
            best[key] = r

    # Group contacts by company.
    contacts_by_company: dict[str, list[dict]] = {}
    for c in contacts:
        key = normalize_name(c.get("company", ""))
        contacts_by_company.setdefault(key, []).append(c)

    rows: list[dict] = []
    for key, r in best.items():
        tier = (r.get("final_tier") or r.get("tier") or "").upper()
        if min_tier and _TIER_ORDER.get(tier, 9) > tier_cap:
            continue
        company_contacts = contacts_by_company.get(key, [])
        if company_contacts:
            for c in company_contacts:
                rows.append(_master_row(config, r, tier, c))
        else:
            rows.append(_master_row(config, r, tier, {}))

    rows.sort(key=lambda x: (_TIER_ORDER.get(x["tier"], 9), -_num(x["score"])))
    _write_csv(rows, out / "master.csv")
    _write_xlsx(rows, out / "master.xlsx")
    print(f"Master: {len(rows)} rows -> {out / 'master.csv'} (+ .xlsx)")
    return rows


def _score(r: dict) -> float:
    return _num(r.get("score"))


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _master_row(config: CampaignConfig, r: dict, tier: str, c: dict) -> dict:
    return {
        "tier": tier,
        "score": r.get("score", ""),
        "company": r.get("company", ""),
        "website": r.get("website", ""),
        "country": r.get("country") or config.country,
        "contact_name": c.get("contact_name", ""),
        "title": c.get("title", ""),
        "email": c.get("email", ""),
        "email_status": c.get("email_status", ""),
        "direct_phone": c.get("direct_phone", ""),
        "corporate_phone": c.get("corporate_phone", ""),
        "linkedin": c.get("linkedin", ""),
        "vendor": config.vendor or r.get("product", ""),
        "recommended_products": r.get("recommended_products", ""),
        "fit_summary": r.get("fit_summary", ""),
        "evidence_urls": r.get("evidence_urls", ""),
    }


def _write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MASTER_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _write_xlsx(rows: list[dict], path: Path) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return
    wb = Workbook()
    ws = wb.active
    ws.title = "Master"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2F5496")
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    tier_fill = {
        "A": PatternFill("solid", fgColor="C6EFCE"),
        "B": PatternFill("solid", fgColor="BDD7EE"),
        "C": PatternFill("solid", fgColor="FFF2CC"),
        "D": PatternFill("solid", fgColor="F2F2F2"),
    }
    wrap_cols = {"fit_summary", "evidence_urls", "recommended_products"}

    for col, name in enumerate(MASTER_COLS, 1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    for ri, r in enumerate(rows, 2):
        for ci, name in enumerate(MASTER_COLS, 1):
            cell = ws.cell(row=ri, column=ci, value=r.get(name, ""))
            cell.border = border
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=name in wrap_cols,
                horizontal="center" if name in ("tier", "score") else "left",
            )
            if name == "tier":
                fill = tier_fill.get(str(r.get("tier", "")).upper())
                if fill:
                    cell.fill = fill
                    cell.font = Font(bold=True)

    widths = {"tier": 6, "score": 7, "company": 30, "website": 26, "country": 12,
             "contact_name": 22, "title": 26, "email": 28, "email_status": 12,
             "direct_phone": 16, "corporate_phone": 16, "linkedin": 30,
             "vendor": 14, "recommended_products": 34, "fit_summary": 60,
             "evidence_urls": 40}
    for col, name in enumerate(MASTER_COLS, 1):
        ws.column_dimensions[get_column_letter(col)].width = widths.get(name, 18)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    try:
        wb.save(path)
    except PermissionError:
        print(f"  !! could not write {path.name} (is it open in Excel?). CSV written OK.")
