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
    paras = body.strip().split("\n\n")
    esc = lambda t: (t.replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace("\n", "<br>\n"))
    divs = "\n".join(f"<p>{esc(p.strip())}</p>" for p in paras if p.strip())
    return (f'<html><body style="font-family: Calibri, Arial, sans-serif; '
            f'font-size: 11pt; color: #000;">\n{divs}\n</body></html>')


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
