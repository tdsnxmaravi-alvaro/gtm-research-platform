"""Write Outlook-ready .eml draft files.

Correctness lessons carried over from the BricsCAD pipeline:
- Serialize with `policy=email.policy.SMTP` (CRLF line endings) so Outlook Classic
  does not corrupt the body via quoted-printable re-wrapping.
- Add `X-Unsent: 1` so double-clicking opens an editable draft ready to Send.
"""

from __future__ import annotations

import email.policy
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, formataddr
from pathlib import Path


def _plain_to_html(body: str) -> str:
    """Render the plain body inside a clean, bordered branded box."""
    paras = body.strip().split("\n\n")

    def esc(t: str) -> str:
        return (t.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>\n"))

    inner = "\n".join(
        f'<p style="margin:0 0 12px 0;">{esc(p.strip())}</p>'
        for p in paras if p.strip()
    )
    return (
        '<html><body style="margin:0; padding:24px; background:#f4f5f7; '
        'font-family: Aptos, Calibri, Arial, sans-serif; font-size:11pt; color:#1a1a1a;">'
        '<div style="max-width:640px; margin:0 auto; background:#ffffff; '
        'border:1px solid #e1e4e8; border-radius:8px; overflow:hidden;">'
        '<div style="height:6px; background:#0f4c81;"></div>'
        f'<div style="padding:28px 32px; line-height:1.5;">{inner}</div>'
        '<div style="padding:14px 32px; border-top:1px solid #eee; '
        'background:#fafbfc; font-size:9pt; color:#8a8f98;">TD SYNNEX</div>'
        '</div></body></html>'
    )


# Marker in a branded sample .eml where the per-company body is injected.
BODY_MARKER = "{{BODY}}"


def _branded_html(body: str, logo_cid: str | None = None) -> str:
    """Branded box with an optional top banner logo (inline CID) + the body.

    The generated content sits inside a bordered card; when a logo is supplied it
    spans the top like the sample outreach template, otherwise a thin brand bar is
    used. The signature is expected to be part of `body`.
    """
    inner = _body_to_html_paragraphs(body)
    banner = (
        f'<img src="cid:{logo_cid}" alt="" '
        'style="display:block; width:100%; max-width:640px; height:auto; border:0;">'
        if logo_cid
        else '<div style="height:6px; background:#0f4c81;"></div>'
    )
    return (
        '<html><body style="margin:0; padding:24px; background:#f4f5f7; '
        'font-family: Aptos, Calibri, Arial, sans-serif; font-size:11pt; color:#1a1a1a;">'
        '<div style="max-width:640px; margin:0 auto; background:#ffffff; '
        'border:1px solid #e1e4e8; border-radius:8px; overflow:hidden;">'
        f'{banner}'
        f'<div style="padding:28px 32px; line-height:1.5;">{inner}</div>'
        '</div></body></html>'
    )


def _body_to_html_paragraphs(body: str) -> str:
    def esc(t: str) -> str:
        return (t.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>\n"))

    return "\n".join(
        f'<p style="margin:0 0 12px 0;">{esc(p.strip())}</p>'
        for p in body.strip().split("\n\n") if p.strip()
    )


def load_eml_template(path: str | Path) -> tuple[str | None, list[dict]]:
    """Load a branded sample .eml.

    Returns (template_html, inline_images). `template_html` is the sample's HTML
    part (should contain the {{BODY}} marker where the per-company message goes);
    the surrounding banner/signature box is preserved as-is. `inline_images` are
    the referenced Content-ID images (banner/logo) carried over so the box renders.
    """
    raw = Path(path).read_bytes()
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    html: str | None = None
    images: list[dict] = []
    for part in msg.walk():
        if part.get_content_type() == "text/html" and html is None:
            html = part.get_content()
        elif part.get_content_maintype() == "image":
            cid = (part.get("Content-ID") or "").strip().strip("<>")
            data = part.get_payload(decode=True)
            if cid and data:
                images.append({"cid": cid, "subtype": part.get_content_subtype(),
                               "data": data})
    return html, images


def apply_template(template_html: str, body: str) -> str | None:
    """Inject the body into the template's {{BODY}} marker. None if no marker."""
    if BODY_MARKER not in template_html:
        return None
    return template_html.replace(BODY_MARKER, _body_to_html_paragraphs(body))


def write_eml(
    path: str | Path,
    *,
    to_email: str,
    subject: str,
    body: str,
    to_name: str = "",
    from_email: str = "",
    from_name: str = "",
    html_body: str | None = None,
    template_eml: str | Path | None = None,
    logo_path: str | Path | None = None,
) -> Path:
    """Write one editable .eml draft. Returns the path.

    When `template_eml` points to a branded sample (with a {{BODY}} marker), its
    box + inline images are reused. Otherwise, when `logo_path` is set, the built-in
    branded frame is used with that logo as the top banner. Falls back to the plain
    branded box when neither is provided.
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    if from_email:
        msg["From"] = formataddr((from_name or None, from_email))
    msg["To"] = formataddr((to_name or None, to_email)) if to_email else (to_name or "")
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg["X-Unsent"] = "1"  # Outlook: open as editable draft

    final_html = html_body
    inline_images: list[dict] = []
    if final_html is None and template_eml:
        try:
            tpl_html, imgs = load_eml_template(template_eml)
            applied = apply_template(tpl_html, body) if tpl_html else None
            if applied is not None:
                final_html = applied
                inline_images = imgs
        except (OSError, ValueError):
            final_html = None  # fall back below

    if final_html is None and logo_path:
        try:
            data = Path(logo_path).read_bytes()
            subtype = (Path(logo_path).suffix.lstrip(".").lower() or "png")
            if subtype == "jpg":
                subtype = "jpeg"
            cid = make_msgid()[1:-1]  # unique id, no angle brackets
            final_html = _branded_html(body, logo_cid=cid)
            inline_images = [{"cid": cid, "subtype": subtype, "data": data}]
        except (OSError, ValueError):
            final_html = None  # fall back to the built-in box

    msg.set_content(body)
    msg.add_alternative(final_html or _plain_to_html(body), subtype="html")

    if inline_images:
        html_part = msg.get_payload()[-1]
        for im in inline_images:
            html_part.add_related(im["data"], maintype="image",
                                  subtype=im["subtype"], cid=f"<{im['cid']}>")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(msg.as_bytes(policy=email.policy.SMTP))
    return path
