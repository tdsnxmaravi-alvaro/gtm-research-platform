"""Enrichment stage — resolve decision-maker contacts for qualified companies.

Two provider paths:
  - Apollo (`apollo`): people search + person enrich (emails), plus optional
    async phone reveals when want=emails+phones.
  - LARA agent (`lara`): web-search contact resolution, no Apollo credits.

Selection and options come from the campaign config's `Enrichment` block.
"""

from .runner import run_enrichment
from .models import EnrichedContact, CONTACT_COLS
from .domains import extract_domain
from .apollo import (
    ApolloClient, enrich_company,
    PhoneRevealStore, fire_reveals, poll_reveals, merge_phones,
)
from .lara_agent import build_lara_enrichment_provider, enrich_company_lara

__all__ = [
    "run_enrichment",
    "EnrichedContact",
    "CONTACT_COLS",
    "extract_domain",
    "ApolloClient",
    "enrich_company",
    "PhoneRevealStore",
    "fire_reveals",
    "poll_reveals",
    "merge_phones",
    "build_lara_enrichment_provider",
    "enrich_company_lara",
]
