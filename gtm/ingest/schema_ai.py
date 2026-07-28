"""AI-assisted column mapping for provided lists (optional, PII-minimized).

A thin LARA "schema mapper" agent maps a stakeholder spreadsheet's arbitrary
column names to our canonical schema (company / website / country / context).
The deterministic layer in `parser.py` still does all counting/validation; this
only adds intelligent header mapping for non-standard files.

PRIVACY: we send ONLY the headers plus a few sample values from NON-sensitive
columns. Columns that look like email / phone / contact / id are excluded so no
personal data leaves the machine for schema detection.

Configure (optional) in .env — falls back to the rules-based mapper if absent:
    LARA_SCHEMA_ASSISTANT_ID=<thin schema-mapper agent, web search OFF>
    LARA_SCHEMA_API_KEY=<per-agent key>   # optional; falls back to LARA_API_KEY
"""

from __future__ import annotations

import ast
import json
import os
import re

from ..providers.lara import LaraProvider

# Headers whose values must NOT be sent to the AI (PII / identifiers).
_PII_HEADER_RE = re.compile(
    r"e-?mail|correo|phone|tel[eé]|contact|persona|dni|nif|cif|address|direcci|"
    r"partner\s*id|customer\s*id",
    re.I,
)

_SCHEMA_PROMPT = """\
You map a spreadsheet's columns to a canonical schema for a company-qualification
pipeline. You are given the column headers and a few sample values from
non-sensitive columns (email/phone/contact columns are intentionally omitted).

Return ONLY a JSON object (no prose, no fences):
{
  "company_column": "<exact header holding the company / reseller / account name>",
  "website_column": "<exact header holding the website / URL / domain, or empty>",
  "country_column": "<exact header for country, or empty>",
  "context_columns": ["<headers useful as qualification context: software in use, sector, industry, size, employees>"],
  "warnings": ["<short data-quality or missing-field notes>"]
}
Rules:
- Use the EXACT header strings as given.
- If there is no website/URL column, set "website_column" to "".
- Do not invent columns that are not in the input.
- Keep warnings short and factual.
- Output MUST be valid JSON: use double quotes for every key and string value
  (not Python-style single quotes), and return the object only."""


def _build_provider() -> LaraProvider | None:
    """Build the LARA schema-mapper provider from env, or None if unconfigured."""
    api_url = os.getenv("LARA_API_URL")
    api_key = os.getenv("LARA_SCHEMA_API_KEY") or os.getenv("LARA_API_KEY")
    assistant = os.getenv("LARA_SCHEMA_ASSISTANT_ID")
    if not (api_url and api_key and assistant):
        return None
    return LaraProvider("lara-schema", api_url, api_key, assistant, web_search=False)


def ai_available() -> bool:
    """True if the schema-mapper agent is configured in the environment."""
    return _build_provider() is not None


def _safe_samples(headers: list[str], rows: list[dict], per_col: int = 3) -> dict:
    """Collect a few sample values per NON-sensitive column."""
    out: dict[str, list[str]] = {}
    for h in headers:
        if not h or _PII_HEADER_RE.search(h):
            continue
        vals: list[str] = []
        for r in rows:
            v = r.get(h)
            if v not in (None, ""):
                vals.append(str(v)[:80])
            if len(vals) >= per_col:
                break
        out[h] = vals
    return out


def _parse_mapping(text: str) -> dict | None:
    """Parse the agent's mapping object, tolerating single-quoted (Python-style)
    output as well as strict JSON."""
    from .parser import _extract_json

    data = _extract_json(text)
    if isinstance(data, dict):
        return data
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if m:
        try:
            obj = ast.literal_eval(m.group(0))
            if isinstance(obj, dict):
                return obj
        except (ValueError, SyntaxError):
            return None
    return None


def ai_map_columns(headers: list[str], rows: list[dict],
                   provider: LaraProvider | None = None,
                   retries: int = 2) -> dict | None:
    """Ask the schema-mapper agent to map columns. Returns a dict or None.

    Result keys: company_column, website_column, country_column,
    context_columns[], warnings[]. Returns None if the agent is unconfigured or
    no attempt yields a parseable object. Retries a few times because models are
    occasionally non-deterministic about output format.
    """
    provider = provider or _build_provider()
    if provider is None:
        return None
    payload = {
        "headers": [h for h in headers if h],
        "samples": _safe_samples(headers, rows),
    }
    prompt = _SCHEMA_PROMPT + "\n\nINPUT:\n" + json.dumps(payload, ensure_ascii=False)
    for _ in range(max(1, retries)):
        try:
            resp = provider.send(prompt)
        except Exception:  # noqa: BLE001 - never block inspection on the AI call
            continue
        mapping = _parse_mapping(resp.text)
        if mapping is not None:
            return mapping
    return None


def overrides_from_ai(mapping: dict) -> dict[str, str]:
    """Turn an AI mapping into a header-lower -> canonical override dict."""
    out: dict[str, str] = {}
    if not isinstance(mapping, dict):
        return out
    if mapping.get("company_column"):
        out[str(mapping["company_column"]).strip().lower()] = "company"
    if mapping.get("website_column"):
        out[str(mapping["website_column"]).strip().lower()] = "website"
    if mapping.get("country_column"):
        out[str(mapping["country_column"]).strip().lower()] = "country"
    return out
