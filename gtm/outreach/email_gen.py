"""Outreach email generation.

Deterministic bilingual template by default (no cost); optional LARA outreach
agent (LARA_OUTREACH_ASSISTANT_ID) for fully personalized copy.
"""

from __future__ import annotations

import json
import os
import re
import ast

from ..config.schema import CampaignConfig, language_for_country


def _first_name(full: str) -> str:
    full = (full or "").strip()
    return full.split()[0] if full else ""


def _short(text: str, n: int = 220) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def render_template(config: CampaignConfig, row: dict) -> tuple[str, str]:
    """Return (subject, body) from the built-in bilingual template.

    Language is derived from the reseller's own country when available (e.g. a
    Portuguese partner gets pt), else the campaign/outreach language.
    """
    lang = (language_for_country(row.get("country"))
            or config.outreach.language or config.language or "en").lower()
    product = row.get("product") or (config.products[0].name if config.products else "our solution")
    company = row.get("company", "")
    first = _first_name(row.get("contact_name", ""))
    rec = row.get("recommended_products", "")
    fit = _short(row.get("fit_summary", ""))
    vp = _short(config.products[0].value_prop if config.products else "", 200)
    sig_name = (config.outreach.sender_name or "").strip()
    signoff_lines = [sig_name, "TD SYNNEX"] if sig_name else ["TD SYNNEX"]

    if lang.startswith("es"):
        greet = f"Hola {first}:" if first else "Hola:"
        subject = config.outreach.subject or f"{company} × {product}: una oportunidad para tu portfolio"
        parts = [
            greet,
            f"Te escribo desde TD SYNNEX sobre {product}. {vp}".strip(),
            f"Según nuestro análisis, {company} encaja bien para incorporarlo a su portfolio: {fit}".strip(),
        ]
        if rec:
            parts.append(f"Te recomendaríamos empezar por: {rec}.")
        parts.append("¿Tendrías disponibilidad para una breve llamada y explorarlo?")
        parts.append("\n".join(["Un saludo,", *signoff_lines]))
    elif lang.startswith("pt"):
        greet = f"Olá {first}," if first else "Olá,"
        subject = config.outreach.subject or f"{company} × {product}: uma oportunidade para o seu portfólio"
        parts = [
            greet,
            f"Escrevo da TD SYNNEX sobre {product}. {vp}".strip(),
            f"Segundo a nossa análise, a {company} encaixa bem para o incorporar ao seu portfólio: {fit}".strip(),
        ]
        if rec:
            parts.append(f"Recomendaríamos começar por: {rec}.")
        parts.append("Teria disponibilidade para uma breve chamada para explorá-lo?")
        parts.append("\n".join(["Cumprimentos,", *signoff_lines]))
    else:
        greet = f"Hi {first}," if first else "Hi,"
        subject = config.outreach.subject or f"{company} × {product}: a fit worth a conversation"
        parts = [
            greet,
            f"I'm reaching out from TD SYNNEX about {product}. {vp}".strip(),
            f"Based on our research, {company} looks like a strong fit to add it to your portfolio: {fit}".strip(),
        ]
        if rec:
            parts.append(f"We'd suggest starting with: {rec}.")
        parts.append("Would you be open to a short call to explore it?")
        parts.append("\n".join(["Best regards,", *signoff_lines]))

    return subject, "\n\n".join(parts)


def _lara_agent():
    """Build a LARA outreach provider from env, or None if unconfigured."""
    api_url = os.getenv("LARA_API_URL")
    api_key = os.getenv("LARA_OUTREACH_API_KEY") or os.getenv("LARA_API_KEY")
    assistant = os.getenv("LARA_OUTREACH_ASSISTANT_ID")
    if not (api_url and api_key and assistant):
        return None
    from ..providers.lara import LaraProvider
    return LaraProvider("lara-outreach", api_url, api_key, assistant, web_search=False)


def generate_email(config: CampaignConfig, row: dict, use_agent: bool = False) -> tuple[str, str]:
    """Return (subject, body). Uses the LARA agent when requested + configured,
    else the deterministic template."""
    if use_agent:
        prov = _lara_agent()
        if prov is not None:
            out = _agent_email(prov, config, row)
            if out:
                return out
    return render_template(config, row)


def _agent_email(prov, config: CampaignConfig, row: dict) -> tuple[str, str] | None:
    lang = config.outreach.language or config.language or "en"
    product = row.get("product") or (config.products[0].name if config.products else "")
    prompt = (
        "Write a concise, warm B2B outreach email (no fluff) for a channel/reseller "
        f"recruitment motion. Language: {lang}. Product: {product}. "
        f"Company: {row.get('company','')}. Contact: {row.get('contact_name','')} "
        f"({row.get('title','')}). Why they fit: {row.get('fit_summary','')}. "
        f"Recommended products: {row.get('recommended_products','')}. "
        f"Sender: {config.outreach.sender_name or 'TD SYNNEX'}.\n\n"
        'Return ONLY JSON: {"subject": "...", "body": "..."} with \\n line breaks in body.'
    )
    try:
        resp = prov.send(prompt)
    except Exception:  # noqa: BLE001
        return None
    m = re.search(r"\{.*\}", resp.text or "", re.DOTALL)
    if not m:
        return None
    data = None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        try:
            # Models sometimes return a Python-style dict (single quotes).
            obj = ast.literal_eval(m.group(0))
            if isinstance(obj, dict):
                data = obj
        except (ValueError, SyntaxError):
            return None
    if not isinstance(data, dict):
        return None
    subj, body = data.get("subject"), data.get("body")
    if subj and body:
        return str(subj), str(body)
    return None
