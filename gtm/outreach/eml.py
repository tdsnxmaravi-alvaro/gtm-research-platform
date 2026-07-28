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
) -> Path:
    """Write one editable .eml draft. Returns the path."""
    msg = EmailMessage()
    msg["Subject"] = subject
    if from_email:
        msg["From"] = formataddr((from_name or None, from_email))
    msg["To"] = formataddr((to_name or None, to_email)) if to_email else (to_name or "")
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg["X-Unsent"] = "1"  # Outlook: open as editable draft

    msg.set_content(body)
    msg.add_alternative(html_body or _plain_to_html(body), subtype="html")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(msg.as_bytes(policy=email.policy.SMTP))
    return path
