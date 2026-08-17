"""Outreach runner — generate emails + .eml drafts from the master list."""

from __future__ import annotations

import re
from pathlib import Path

from ..config.schema import CampaignConfig
from ..io import read_csv_dicts
from .email_gen import generate_outreach
from .eml import write_eml

_TIER_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "": 9}


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())[:60] or "contact"


def run_outreach(
    config: CampaignConfig,
    *,
    min_tier: str | None = None,
    limit: int = 0,
    use_agent: bool = True,
    out_dir: str | Path | None = None,
    progress_cb=None,
) -> list[dict]:
    """Generate .eml drafts for master contacts with an email at/above min_tier.

    By default personalizes each email with the LARA outreach agent
    (LARA_OUTREACH_ASSISTANT_ID); falls back to the deterministic bilingual
    template when the agent is not configured or a call fails.
    """
    out = Path(out_dir or (Path("campaigns") / config.name))
    master_path = out / "master.csv"
    if not master_path.exists():
        print("No master.csv — run `gtm consolidate` first.")
        return []

    rows = read_csv_dicts(master_path)

    cap = _TIER_ORDER.get((min_tier or config.outreach.min_tier or "B").upper(), 1)

    # One draft per COMPANY: pick the primary contact (best title with an email).
    priority = ["president", "ceo", "owner", "founder", "managing director",
                "director", "vp", "vice president", "head", "manager"]

    def _rank(r: dict) -> int:
        t = (r.get("title") or "").lower()
        return next((i for i, p in enumerate(priority) if p in t), 99)

    primary: dict[str, dict] = {}
    for r in rows:
        if not r.get("email"):
            continue
        if _TIER_ORDER.get((r.get("tier") or "").upper(), 9) > cap:
            continue
        key = (r.get("company") or "").strip().lower()
        cur = primary.get(key)
        if cur is None or _rank(r) < _rank(cur):
            primary[key] = r

    targets = sorted(primary.values(),
                     key=lambda x: (_TIER_ORDER.get((x.get("tier") or "").upper(), 9),
                                    -_num(x.get("score"))))
    if limit:
        targets = targets[:limit]

    eml_dir = out / "eml"
    if use_agent:
        from .email_gen import _lara_agent
        mode = "LARA agent (personalized)" if _lara_agent() is not None else "template (agent not configured)"
    else:
        mode = "template (forced)"
    print(f"Outreach generator: {mode}")

    # Resolve the branded frame: custom .eml > custom logo > vendor .oft > built-in.
    template_eml = config.outreach.template_eml
    logo_path = config.outreach.logo_path
    if not template_eml and not logo_path and config.vendor:
        from .oft import vendor_template_eml
        template_eml = vendor_template_eml(config.vendor, out.parent / ".templates")
        if template_eml:
            print(f"Outreach template: vendor '{config.vendor}' -> {template_eml}")

    drafts: list[dict] = []
    outreach_rows: list[dict] = []
    for i, r in enumerate(targets, 1):
        phone = (r.get("direct_phone") or r.get("corporate_phone") or "").strip()
        pkg = generate_outreach(config, r, use_agent=use_agent,
                                want_talking_points=bool(phone))
        subject, body = pkg["subject"], pkg["body"]
        fname = f"{r.get('tier','')}_{_safe(r.get('company',''))}_{_safe(r.get('contact_name',''))}.eml"
        path = write_eml(
            eml_dir / fname,
            to_email=r["email"], to_name=r.get("contact_name", ""),
            subject=subject, body=body,
            from_email=config.outreach.sender_email,
            from_name=config.outreach.sender_name,
            template_eml=template_eml,
            logo_path=logo_path,
        )
        drafts.append({"company": r.get("company"), "email": r["email"], "eml": str(path)})
        outreach_rows.append({
            "company": r.get("company", ""), "tier": r.get("tier", ""),
            "score": r.get("score", ""), "contact_name": r.get("contact_name", ""),
            "title": r.get("title", ""), "email": r.get("email", ""), "phone": phone,
            "subject": subject, "body": body,
            "followup_subject": pkg["followup_subject"], "followup_body": pkg["followup_body"],
            "talking_points": pkg["talking_points"],
        })
        if progress_cb:
            progress_cb(i, len(targets))

    # Add/refresh the 'Outreach' tab on the existing master.xlsx (no extra file).
    if outreach_rows:
        from ..consolidate.master import write_outreach_sheet
        write_outreach_sheet(out, outreach_rows)

    print(f"Outreach: {len(drafts)} .eml drafts -> {eml_dir}")
    return drafts
