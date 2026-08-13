"""Persistent Apollo phone-delivery service (webhook receiver + cloudflared tunnel).

Non-technical users shouldn't touch a terminal or .env. When an enrich stage needs
phones, `ensure_phone_delivery` starts (once) a receiver + tunnel for that campaign
and keeps them alive for the process lifetime — Apollo delivers numbers async (~40
min), so the receiver must outlive the stage. Falls back to polling when cloudflared
is unavailable. Idempotent per campaign; torn down at process exit.
"""

from __future__ import annotations

import atexit
import socket
import threading

from gtm.enrichment.apollo.tunnel import (
    cloudflared_available, open_quick_tunnel, publish_webhook_url,
)
from gtm.enrichment.apollo.webhook import serve_webhook_bg

_LOCK = threading.Lock()
_SERVICES: dict[str, dict] = {}  # campaign name -> {server, tunnel, url, port, mode}
_PATH = "/apollo-webhook"


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def ensure_phone_delivery(name: str, store_path) -> dict:
    """Ensure a phone-delivery service is running for `name`. Returns status:
    {"mode": "webhook"|"polling", "url": str|None}. Safe to call repeatedly."""
    import os

    with _LOCK:
        existing = _SERVICES.get(name)
        if existing:
            return {"mode": existing["mode"], "url": existing.get("url")}

        # No cloudflared -> we can't receive callbacks publicly; use polling.
        if not cloudflared_available():
            _SERVICES[name] = {"mode": "polling", "server": None, "tunnel": None}
            return {"mode": "polling", "url": None}

        port = _free_port()
        server = serve_webhook_bg(store_path, port=port, path=_PATH)
        proc, url = open_quick_tunnel(port)
        if not url:
            # Tunnel didn't come up -> stop the receiver, degrade to polling.
            try:
                server.shutdown()
            except Exception:  # noqa: BLE001
                pass
            if proc is not None:
                try:
                    proc.terminate()
                except OSError:
                    pass
            _SERVICES[name] = {"mode": "polling", "server": None, "tunnel": None}
            return {"mode": "polling", "url": None}

        full = publish_webhook_url(url, _PATH)
        os.environ["APOLLO_WEBHOOK_URL"] = full
        _SERVICES[name] = {"mode": "webhook", "server": server, "tunnel": proc,
                           "url": full, "port": port}
        return {"mode": "webhook", "url": full}


def _shutdown_all() -> None:
    with _LOCK:
        for svc in _SERVICES.values():
            server = svc.get("server")
            if server is not None:
                try:
                    server.shutdown()
                except Exception:  # noqa: BLE001
                    pass
            proc = svc.get("tunnel")
            if proc is not None:
                try:
                    proc.terminate()
                except OSError:
                    pass
        _SERVICES.clear()


atexit.register(_shutdown_all)
