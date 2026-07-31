"""LARA enrichment agent — resolve contacts via web search (no Apollo credits).

Uses a thin generalist LARA assistant (assistant id from
LARA_ENRICHMENT_ASSISTANT_ID) to find decision-maker contacts for a company and
parses the fixed JSON schema into EnrichedContact rows.
"""

from __future__ import annotations

import json
import os
import re

from ...providers.lara import LaraProvider
from ..domains import extract_domain
from ..models import EnrichedContact
from .prompt import build_enrichment_prompt


def build_lara_enrichment_provider(load_env: bool = True) -> LaraProvider:
    """Build a LARA provider for the enrichment assistant from env vars."""
    if load_env:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
    api_url = os.getenv("LARA_API_URL")
    api_key = os.getenv("LARA_ENRICHMENT_API_KEY") or os.getenv("LARA_API_KEY")
    assistant = os.getenv("LARA_ENRICHMENT_ASSISTANT_ID")
    missing = [k for k, v in (("LARA_API_URL", api_url),
                              ("LARA_ENRICHMENT_API_KEY", api_key),
                              ("LARA_ENRICHMENT_ASSISTANT_ID", assistant)) if not v]
    if missing:
        raise ValueError(f"LARA enrichment agent missing env values: {missing}")
    return LaraProvider("lara-enrichment", api_url, api_key, assistant, web_search=True)


def _parse_contacts(text: str) -> list[dict]:
    """Extract the {"contacts": [...]} array from a possibly-noisy response."""
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text or "", re.DOTALL)
    candidate = fence.group(1) if fence else None
    if not candidate:
        m = re.search(r"(\{.*\})", text or "", re.DOTALL)
        candidate = m.group(1) if m else None
    if not candidate:
        return []
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return []
    contacts = data.get("contacts") if isinstance(data, dict) else None
    return contacts if isinstance(contacts, list) else []


def enrich_company_lara(
    provider: LaraProvider,
    row: dict,
    *,
    country: str = "",
    max_contacts: int = 3,
    language: str = "en",
) -> list[EnrichedContact]:
    """Resolve contacts for one qualified company row via the LARA agent."""
    company = (row.get("company") or "").strip()
    if not company:
        return []
    website = row.get("website") or ""
    domain = extract_domain(website)
    tier = str(row.get("final_tier") or row.get("tier") or "")
    score = str(row.get("score") or "")

    prompt = build_enrichment_prompt(
        company, domain, country=country,
        max_contacts=max_contacts, language=language,
    )
    resp = provider.send(prompt)

    contacts: list[EnrichedContact] = []
    for c in _parse_contacts(resp.text)[:max_contacts]:
        if not isinstance(c, dict):
            continue
        phone = str(c.get("phone", "")).strip()
        ptype = str(c.get("phone_type", "")).strip().lower()
        # LARA finds public numbers (usually a corporate/main line); only treat as
        # a direct dial when the agent explicitly says so.
        direct = phone if (phone and ptype == "direct") else ""
        corporate = phone if (phone and ptype != "direct") else ""
        contacts.append(EnrichedContact(
            company=company, domain=domain, tier=tier, score=score,
            contact_name=str(c.get("contact_name", "")).strip(),
            title=str(c.get("title", "")).strip(),
            email=str(c.get("email", "")).strip(),
            email_status="lara_web" if c.get("email") else "",
            direct_phone=direct, corporate_phone=corporate,
            phone_reveal_status="lara_web" if phone else "",
            linkedin=str(c.get("linkedin", "")).strip(),
            source="lara",
        ))
    return contacts
