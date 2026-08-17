"""Shared enrichment data structures and output columns."""

from __future__ import annotations

from dataclasses import dataclass, asdict


# Output columns for the enriched contacts CSV (stable order).
CONTACT_COLS = [
    "company", "domain", "tier", "score",
    "apollo_id", "contact_name", "title",
    "email", "email_status", "personal_emails",
    "direct_phone", "corporate_phone", "phone_reveal_status",
    "linkedin", "city", "state", "country", "source",
]


@dataclass
class EnrichedContact:
    """One contact resolved for a qualified company."""

    company: str = ""
    domain: str = ""
    tier: str = ""
    score: str = ""
    apollo_id: str = ""
    contact_name: str = ""
    title: str = ""
    email: str = ""
    email_status: str = ""
    personal_emails: str = ""
    direct_phone: str = ""
    corporate_phone: str = ""
    phone_reveal_status: str = ""
    linkedin: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    source: str = ""  # apollo | lara

    def to_row(self) -> dict:
        return {k: asdict(self).get(k, "") for k in CONTACT_COLS}
