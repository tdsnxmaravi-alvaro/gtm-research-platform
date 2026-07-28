"""Outreach runner — generate emails + .eml drafts from the master list."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from ..config.schema import CampaignConfig
from .email_gen import generate_email
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

    with open(master_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

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

    drafts: list[dict] = []
    for r in targets:
        subject, body = generate_email(config, r, use_agent=use_agent)
        fname = f"{r.get('tier','')}_{_safe(r.get('company',''))}_{_safe(r.get('contact_name',''))}.eml"
        path = write_eml(
            eml_dir / fname,
            to_email=r["email"], to_name=r.get("contact_name", ""),
            subject=subject, body=body,
            from_email=config.outreach.sender_email,
            from_name=config.outreach.sender_name,
        )
        drafts.append({"company": r.get("company"), "email": r["email"], "eml": str(path)})

    print(f"Outreach: {len(drafts)} .eml drafts -> {eml_dir}")
    return drafts
