"""Network/TLS setup.

Corporate networks (e.g. TD SYNNEX) often terminate TLS with an internal proxy
whose root CA is in the OS trust store but NOT in certifi's bundle, which makes
`requests` fail with CERTIFICATE_VERIFY_FAILED for some hosts (e.g. Apollo).

`truststore` routes Python's SSL verification through the operating system trust
store, which already trusts the corporate CA. This is the secure fix (we do NOT
disable verification). Set GTM_NO_TRUSTSTORE=1 to opt out.
"""

from __future__ import annotations

import os

_INJECTED = False


def enable_system_trust_store() -> bool:
    """Route SSL verification through the OS trust store. Idempotent.

    Returns True if injection is active, False if skipped/unavailable.
    """
    global _INJECTED
    if _INJECTED or os.getenv("GTM_NO_TRUSTSTORE") == "1":
        return _INJECTED
    try:
        import truststore
        truststore.inject_into_ssl()
        _INJECTED = True
    except Exception:  # noqa: BLE001 - never block on TLS setup
        _INJECTED = False
    return _INJECTED
