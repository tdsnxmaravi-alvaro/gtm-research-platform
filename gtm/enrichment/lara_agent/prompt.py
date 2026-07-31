"""Prompt for the LARA enrichment agent.

The agent is a thin generalist LARA assistant with web search. Instructions live
here (not in the agent config) so the same assistant works for any product,
vertical, or country. It resolves decision-maker contacts for one company and
returns a fixed JSON schema.
"""

from __future__ import annotations

ENRICHMENT_OUTPUT_SCHEMA = """
Return ONLY a JSON object, no prose, with this exact shape:
{
  "contacts": [
    {
      "contact_name": "Full Name",
      "title": "Job title",
      "email": "name@company.com or empty string if not found",
      "phone": "public phone in international format (+countrycode...) or empty string",
      "phone_type": "direct | corporate | empty (empty if no phone)",
      "linkedin": "https://linkedin.com/in/... or empty string",
      "source_url": "URL where you found this contact"
    }
  ]
}
Rules:
- Only include real, decision-maker contacts (owner, founder, C-suite, VP, head,
  director, sales/channel manager). Prefer the most senior/relevant first.
- NEVER invent an email or a phone. If you cannot verify one from a public source,
  use an empty string. Do NOT guess personal mobile numbers.
- "phone_type" is "direct" only for a personal/direct line, "corporate" for a main
  or department line; empty when there is no phone.
- Every contact MUST have a source_url you actually consulted.
- If you find no contacts, return {"contacts": []}.
"""


def build_enrichment_prompt(
    company: str,
    domain: str,
    *,
    country: str = "",
    max_contacts: int = 3,
    language: str = "en",
) -> str:
    """Build the LARA enrichment prompt for a single company."""
    loc = f" based in {country}" if country else ""
    return (
        f"You are a B2B contact-research assistant with web search.\n"
        f"Find up to {max_contacts} decision-maker contacts at the company "
        f'"{company}"{loc} (website/domain: {domain or "unknown"}).\n'
        f"Use the company website, LinkedIn, and public sources. "
        f"Respond in {language}.\n\n"
        f"{ENRICHMENT_OUTPUT_SCHEMA}"
    )
