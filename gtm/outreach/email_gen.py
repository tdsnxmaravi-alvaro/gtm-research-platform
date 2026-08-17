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
from ..config.org import channel_name, org_name


def _first_name(full: str) -> str:
    full = (full or "").strip()
    return full.split()[0] if full else ""


def _short(text: str, n: int = 220) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def render_template(config: CampaignConfig, row: dict) -> tuple[str, str]:
    """Return (subject, body) from the built-in bilingual template.

    Language precedence: an explicit outreach language wins (the user's choice);
    otherwise it is auto-derived from the company's own country (e.g. a Portuguese
    partner gets pt), then the campaign language, then English.
    """
    lang = (config.outreach.language
            or language_for_country(row.get("country"))
            or config.language or "en").lower()
    product = row.get("product") or (config.products[0].name if config.products else "our solution")
    company = row.get("company", "")
    first = _first_name(row.get("contact_name", ""))
    rec = row.get("recommended_products", "")
    fit = _short(row.get("fit_summary", ""))
    vp = _short(config.products[0].value_prop if config.products else "", 200)
    sig_name = (config.outreach.sender_name or "").strip()
    org = org_name(config)
    signoff_lines = [sig_name, org] if sig_name else [org]

    if lang.startswith("es"):
        greet = f"Hola {first}:" if first else "Hola:"
        subject = config.outreach.subject or f"{company} × {product}: una oportunidad para tu portfolio"
        parts = [
            greet,
            f"Te escribo desde {org} sobre {product}. {vp}".strip(),
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
            f"Escrevo da {org} sobre {product}. {vp}".strip(),
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
            f"I'm reaching out from {org} about {product}. {vp}".strip(),
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


def _clean_body(body: str) -> str:
    """Tidy generated copy: unwrap markdown links and collapse duplicate lines
    (the LARA agent sometimes emits '[TD SYNNEX]()' or a doubled sign-off)."""
    body = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", body or "")  # [text](url) -> text
    out: list[str] = []
    for line in body.split("\n"):
        if out and line.strip() and line.strip() == out[-1].strip():
            continue  # drop consecutive duplicate lines
        out.append(line)
    return "\n".join(out).strip()


def generate_email(config: CampaignConfig, row: dict, use_agent: bool = False) -> tuple[str, str]:
    """Return (subject, body). Uses the LARA agent when requested + configured,
    else the deterministic template. Body is tidied either way."""
    pkg = generate_outreach(config, row, use_agent=use_agent, want_talking_points=False)
    return pkg["subject"], pkg["body"]


def generate_outreach(config: CampaignConfig, row: dict, use_agent: bool = False,
                      want_talking_points: bool = False) -> dict:
    """Return the full outreach package for one contact.

    Keys: subject, body, followup_subject, followup_body, talking_points.
    ``talking_points`` is only produced when ``want_talking_points`` is True — i.e.
    a phone number was obtained for the contact (a call script only helps if you
    can call). Missing agent fields fall back to deterministic templates.
    """
    pkg: dict = {}
    if use_agent:
        prov = _lara_agent()
        if prov is not None:
            pkg = _agent_outreach(prov, config, row, want_talking_points) or {}

    subject = pkg.get("subject")
    body = pkg.get("body")
    if not subject or not body:
        subject, body = render_template(config, row)
    followup_subject = pkg.get("followup_subject") or _followup_subject(subject)
    followup_body = pkg.get("followup_body") or _template_followup(config, row)
    talking_points = ""
    if want_talking_points:
        talking_points = pkg.get("talking_points") or _template_talking_points(config, row)
    return {
        "subject": subject,
        "body": _clean_body(body),
        "followup_subject": followup_subject,
        "followup_body": _clean_body(followup_body),
        "talking_points": _clean_body(talking_points),
    }


def _followup_subject(subject: str) -> str:
    s = (subject or "").strip()
    return s if s.lower().startswith("re:") else f"Re: {s}"


def _template_followup(config: CampaignConfig, row: dict) -> str:
    """Deterministic short follow-up email body (used when no agent copy)."""
    lang = (config.outreach.language
            or language_for_country(row.get("country"))
            or config.language or "en").lower()
    first = _first_name(row.get("contact_name", ""))
    company = row.get("company", "")
    product = row.get("product") or (config.products[0].name if config.products else "our solution")
    sig_name = (config.outreach.sender_name or "").strip()
    org = org_name(config)
    channel = channel_name(config)
    if lang.startswith("es"):
        greet = f"Hola {first}:" if first else "Hola:"
        lines = [greet,
                 f"Retomo mi mensaje anterior sobre {product} para {company}.",
                 "Sigue en pie una breve llamada para verlo con calma; "
                 "si lo lleva otra persona, con gusto me pones en contacto.",
                 "\n".join(["Un saludo,", sig_name, org] if sig_name
                           else ["Un saludo,", f"El equipo {channel} de {org}"])]
    elif lang.startswith("pt"):
        greet = f"Olá {first}," if first else "Olá,"
        lines = [greet,
                 f"Retomando a minha mensagem anterior sobre {product} para a {company}.",
                 "Continua de pé uma breve chamada para o vermos com calma; "
                 "se for outra pessoa a tratar disto, agradeço que me encaminhe.",
                 "\n".join(["Cumprimentos,", sig_name, org] if sig_name
                           else ["Cumprimentos,", f"A equipa {channel} da {org}"])]
    else:
        greet = f"Hi {first}," if first else "Hi,"
        lines = [greet,
                 f"Circling back on my earlier note about {product} for {company}.",
                 "A short call still stands whenever it suits you; if someone else owns "
                 "this, please point me their way.",
                 "\n".join(["Best regards,", sig_name, org] if sig_name
                           else ["Best regards,", f"The {org} {channel} Team"])]
    return "\n\n".join(lines)


def _template_talking_points(config: CampaignConfig, row: dict) -> str:
    """Deterministic call-script bullets (used when no agent copy)."""
    lang = (config.outreach.language
            or language_for_country(row.get("country"))
            or config.language or "en").lower()
    first = _first_name(row.get("contact_name", ""))
    company = row.get("company", "")
    product = row.get("product") or (config.products[0].name if config.products else "our solution")
    fit = _short(row.get("fit_summary", ""), 160)
    rec = row.get("recommended_products", "")
    org = org_name(config)
    channel = channel_name(config)
    brand = f"{org} {channel}"
    if lang.startswith("es"):
        pts = [
            f"Apertura: {first or 'Hola'}, te llamo de {brand}; sumamos partners de {product} "
            f"donde ya encaja el flujo de trabajo del cliente.",
            f"Encaje: por qué {company} encaja — {fit}." if fit else f"Encaje: {company} encaja bien.",
            f"Historia de ingresos: {product} añade una línea de software (licencias + migración, "
            "formación e implementación).",
            f"Siguiente paso: empezar por {rec}." if rec else "Siguiente paso: una breve llamada para verlo.",
        ]
    elif lang.startswith("pt"):
        pts = [
            f"Abertura: {first or 'Olá'}, ligo da {brand}; estamos a somar parceiros de {product} "
            "onde o fluxo de trabalho do cliente já encaixa.",
            f"Encaixe: porque é que a {company} encaixa — {fit}." if fit else f"Encaixe: a {company} encaixa bem.",
            f"História de receita: {product} acrescenta uma linha de software (licenças + migração, "
            "formação e implementação).",
            f"Próximo passo: começar por {rec}." if rec else "Próximo passo: uma breve chamada.",
        ]
    else:
        pts = [
            f"Opener: {first or 'Hi'}, calling from {brand} — we're adding {product} reseller "
            "partners where that workflow is already part of the customer conversation.",
            f"Fit: why {company} fits — {fit}." if fit else f"Fit: {company} looks like a strong fit.",
            f"Revenue story: {product} adds a software line (licensing plus migration, training and "
            "implementation services).",
            f"Next step: start with {rec}." if rec else "Next step: a short call to explore it.",
        ]
    return "\n".join(f"• {p}" for p in pts)


def _agent_email(prov, config: CampaignConfig, row: dict) -> tuple[str, str] | None:
    pkg = _agent_outreach(prov, config, row, want_talking_points=False)
    if pkg and pkg.get("subject") and pkg.get("body"):
        return str(pkg["subject"]), str(pkg["body"])
    return None


def _agent_outreach(prov, config: CampaignConfig, row: dict,
                    want_talking_points: bool) -> dict | None:
    lang = (config.outreach.language
            or language_for_country(row.get("country"))
            or config.language or "en")
    lang_names = {"en": "English", "es": "Spanish", "pt": "Portuguese",
                  "fr": "French", "de": "German", "it": "Italian"}
    lang_name = lang_names.get(lang, lang)
    product = row.get("product") or (config.products[0].name if config.products else "")
    schema = ('{"subject": "...", "body": "...", '
              '"followup_subject": "...", "followup_body": "..."')
    tp_line = ""
    if want_talking_points:
        schema += ', "talking_points": "..."'
        tp_line = (
            "Also write 'talking_points': 4-6 short bullet lines (each prefixed with '• ', "
            "separated by \\n) as a phone-call script for this contact — an opener, why this "
            "specific company fits, the revenue/margin story, and a soft next step. "
        )
    schema += "}"
    prompt = (
        "Write a concise, warm B2B outreach email (no fluff) for a channel/reseller "
        f"recruitment motion. Write EVERYTHING — subject, body, follow-up and any talking "
        f"points — in {lang_name} ({lang}); do NOT use English unless the language is English. "
        f"Product: {product}. Company: {row.get('company','')}. "
        f"Contact: {row.get('contact_name','')} ({row.get('title','')}). "
        f"Why they fit: {row.get('fit_summary','')}. "
        f"Recommended products: {row.get('recommended_products','')}. "
        f"Sender: {config.outreach.sender_name or org_name(config)}.\n\n"
        "Also write a short follow-up email: 'followup_subject' as 'Re: <the subject>' and a "
        "2-4 line 'followup_body' that politely circles back and restates the single value point. "
        + tp_line +
        f'Return ONLY JSON: {schema} with \\n line breaks inside each body.'
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
    return {k: str(v) for k, v in data.items()
            if k in ("subject", "body", "followup_subject", "followup_body", "talking_points")
            and v}

