"""Domain extraction from noisy website/URL fields.

Ported from the BricsCAD pipeline: handles multi-domain fields, missing scheme,
and rejects obviously-invalid placeholder values.
"""

from __future__ import annotations

from urllib.parse import urlparse

_INVALID_HINTS = ("not found", "n/a", "no website", "unverified", "unknown")


def extract_domain(url: str) -> str:
    """Extract a bare domain from a website/URL value.

    'https://www.ecedesign.com/' -> 'ecedesign.com'
    'lp360.com; geocue.com'      -> 'lp360.com'  (first valid)
    'unknown'                    -> ''
    """
    if not url:
        return ""

    lowered = url.lower().strip()
    if any(hint in lowered for hint in _INVALID_HINTS):
        return ""

    # Multi-domain fields: take the first valid one.
    for sep in (";", ",", "+", "|"):
        if sep in url:
            for part in (p.strip() for p in url.split(sep)):
                got = extract_domain(part)
                if got:
                    return got
            return ""

    if not url.startswith("http"):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        if domain.startswith("www."):
            domain = domain[4:]
        domain = domain.split("/")[0].lower().strip()
        if "." not in domain or " " in domain:
            return ""
        return domain
    except ValueError:
        return ""
