"""Convert a vendor's Outlook `.oft` blank template into a reusable `.eml` template.

The BDR templates share a shape: a banner image (logo), an accent bar, an EMPTY
body cell, and a signature block with placeholders the BDM fills in Outlook. We
inject a ``{{BODY}}`` marker into the empty body cell and carry the inline images,
producing an `.eml` that ``write_eml(template_eml=...)`` renders directly. The
signature is left untouched (each BDM completes it in the draft).
"""

from __future__ import annotations

import email.policy
import re
from email.message import EmailMessage
from pathlib import Path

from .eml import BODY_MARKER

# vendor -> filename keyword in templates/ (DraftSight ships under Dassault).
VENDOR_TEMPLATE_KEY = {
    "Bricsys": "Bricsys",
    "DraftSight": "Dassault",
    "Novade": "Novade",
    "Newforma": "Newforma",
    "Unity": "Unity",
    "Trimble": "Trimble",
}


def templates_dir() -> Path:
    """Directory holding the vendor `.oft` templates (env override or ./templates)."""
    import os
    return Path(os.getenv("GTM_TEMPLATES_DIR", "templates"))


def find_vendor_template(vendor: str, directory: Path | None = None) -> Path | None:
    """Return the `.oft` template file for a vendor, or None."""
    key = VENDOR_TEMPLATE_KEY.get((vendor or "").strip())
    if not key:
        return None
    d = directory or templates_dir()
    if not d.exists():
        return None
    for p in sorted(d.glob("*.oft")):
        if key.lower() in p.name.lower():
            return p
    return None


def _inject_body_marker(html: str) -> str:
    """Insert {{BODY}} into the first empty body cell after the banner image."""
    img = re.search(r'<img[^>]+cid:[^>]+>', html, re.I)
    start = img.end() if img else 0
    head, tail = html[:start], html[start:]

    injected = {"done": False}

    def _once(m: re.Match) -> str:
        if injected["done"]:
            return m.group(0)
        inner = m.group(2)
        text = re.sub(r"<[^>]+>", "", inner).replace("&nbsp;", "").strip()
        if text == "":  # the empty body cell (padding:15pt), not the thin accent bar
            injected["done"] = True
            return m.group(1) + BODY_MARKER + m.group(3)
        return m.group(0)

    tail = re.compile(r"(<td\b[^>]*padding:15[^>]*>)(.*?)(</td>)", re.I | re.S).sub(_once, tail)
    if not injected["done"]:
        # Fallback: drop the body right after the banner image.
        tail = f"<div>{BODY_MARKER}</div>" + tail
    return head + tail


def oft_to_eml(oft_path: str | Path, out_path: str | Path) -> Path:
    """Convert a `.oft` template to an `.eml` template with a {{BODY}} marker."""
    import extract_msg

    msg_o = extract_msg.openMsg(str(oft_path))
    raw = msg_o.htmlBody
    html = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else (raw or "")
    html = _inject_body_marker(html)

    images: list[tuple[str, str, bytes]] = []
    for a in msg_o.attachments:
        cid = (getattr(a, "cid", "") or "").strip("<>")
        data = getattr(a, "data", None)
        mimetype = getattr(a, "mimetype", "") or ""
        if cid and data and mimetype.startswith("image"):
            images.append((cid, mimetype.split("/")[-1] or "png", data))

    msg = EmailMessage()
    msg["Subject"] = "template"
    msg.set_content("template")
    msg.add_alternative(html, subtype="html")
    html_part = msg.get_payload()[-1]
    for cid, subtype, data in images:
        html_part.add_related(data, maintype="image", subtype=subtype, cid=f"<{cid}>")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(msg.as_bytes(policy=email.policy.SMTP))
    return out_path


def vendor_template_eml(vendor: str, cache_dir: Path) -> str | None:
    """Resolve (and cache) a vendor's branded `.eml` template, or None if absent."""
    oft = find_vendor_template(vendor)
    if not oft:
        return None
    eml = Path(cache_dir) / f"{(vendor or 'vendor').strip()}.eml"
    try:
        if not eml.exists() or eml.stat().st_mtime < oft.stat().st_mtime:
            oft_to_eml(oft, eml)
    except Exception:  # noqa: BLE001 - never block outreach on template issues
        return None
    return str(eml)
