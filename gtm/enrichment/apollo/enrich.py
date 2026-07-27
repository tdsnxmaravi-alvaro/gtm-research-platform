"""Apollo email enrichment — resolve decision-maker contacts per company.

Given a qualified company row (company + website), search Apollo for
decision-makers, enrich the top `max_contacts`, and return EnrichedContact rows.
"""

from __future__ import annotations

import time

from ..domains import extract_domain
from ..models import EnrichedContact
from .client import ApolloClient, title_priority


def enrich_company(
    client: ApolloClient,
    row: dict,
    *,
    max_contacts: int = 3,
    delay: float = 0.5,
) -> list[EnrichedContact]:
    """Return enriched contacts for one qualified company row.

    `row` is a research result row (keys: company, website, final_tier/tier, score).
    """
    company = (row.get("company") or "").strip()
    website = row.get("website") or ""
    tier = str(row.get("final_tier") or row.get("tier") or "")
    score = str(row.get("score") or "")

    domain = extract_domain(website)
    if not domain and company:
        domain = client.search_org_domain(company) or ""
        time.sleep(delay)
    if not domain:
        return []

    people, _total = client.search_people_by_domain(domain, per_page=max(10, max_contacts))
    if not people:
        return []

    people.sort(key=lambda p: title_priority(p.get("title", "")))

    contacts: list[EnrichedContact] = []
    for person in people[:max_contacts]:
        pid = person.get("id")
        display = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
        if not pid:
            continue

        enriched = client.enrich_person(pid)
        time.sleep(delay)

        if enriched:
            org = enriched.get("organization") or {}
            phones = enriched.get("phone_numbers") or []
            direct_phone = ", ".join(
                p.get("sanitized_number", "") for p in phones if isinstance(p, dict)
            ).strip(", ")
            corporate = (org.get("primary_phone") or {}).get("number", org.get("phone", ""))
            contacts.append(EnrichedContact(
                company=company, domain=domain, tier=tier, score=score,
                apollo_id=str(enriched.get("id", pid)),
                contact_name=enriched.get("name", display),
                title=enriched.get("title", ""),
                email=enriched.get("email", ""),
                email_status=enriched.get("email_status", ""),
                personal_emails=", ".join(enriched.get("personal_emails") or []),
                direct_phone=direct_phone,
                corporate_phone=corporate or "",
                linkedin=enriched.get("linkedin_url", ""),
                city=enriched.get("city", ""),
                state=enriched.get("state", ""),
                country=enriched.get("country", ""),
                source="apollo",
            ))
        else:
            contacts.append(EnrichedContact(
                company=company, domain=domain, tier=tier, score=score,
                apollo_id=str(pid), contact_name=display,
                title=person.get("title", ""), email=person.get("email", ""),
                email_status="enrich_failed", source="apollo",
            ))
    return contacts
