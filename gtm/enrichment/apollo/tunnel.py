"""Auto-manage a cloudflared quick tunnel for Apollo phone-reveal webhooks.

Non-technical operators shouldn't have to run three commands and hand-edit .env.
`open_quick_tunnel` starts cloudflared and returns the public trycloudflare URL;
the webhook receiver uses it to auto-set APOLLO_WEBHOOK_URL and write it to a small
file the enrich runner reads. Falls back cleanly (returns None) when cloudflared
isn't installed, so callers can degrade to polling.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
from pathlib import Path

_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

# Where the running tunnel publishes its public webhook URL so the enrich runner
# (a different process) can pick it up without any manual .env editing.
WEBHOOK_URL_FILE = Path(".gtm_cache") / "webhook_url.txt"


def parse_tunnel_url(text: str) -> str | None:
    """Extract the https://<random>.trycloudflare.com URL from cloudflared output."""
    m = _URL_RE.search(text or "")
    return m.group(0) if m else None


def cloudflared_available() -> bool:
    return shutil.which("cloudflared") is not None


def open_quick_tunnel(port: int, *, timeout: float = 30.0):
    """Start a cloudflared quick tunnel to localhost:port.

    Returns (proc, url). `url` is None (and proc may be None) if cloudflared is
    missing or the URL doesn't appear within `timeout` — callers should then fall
    back to polling.
    """
    exe = shutil.which("cloudflared")
    if not exe:
        return None, None
    proc = subprocess.Popen(
        [exe, "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    holder: dict = {"url": None}

    def _read() -> None:
        for line in proc.stdout:  # keep draining so the pipe never blocks cloudflared
            if holder["url"] is None:
                u = parse_tunnel_url(line)
                if u:
                    holder["url"] = u

    threading.Thread(target=_read, daemon=True).start()
    # Wait (without blocking forever) for the URL to appear.
    import time
    start = time.time()
    while time.time() - start < timeout and holder["url"] is None and proc.poll() is None:
        time.sleep(0.2)
    return proc, holder["url"]


def publish_webhook_url(url: str, path: str = "/apollo-webhook",
                        file: Path | None = None) -> str:
    """Write the full public webhook URL so other processes can read it."""
    full = url.rstrip("/") + path
    f = Path(file or WEBHOOK_URL_FILE)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(full, encoding="utf-8")
    return full


def read_webhook_url(file: Path | None = None) -> str | None:
    """Read the published webhook URL (used as a fallback to APOLLO_WEBHOOK_URL)."""
    f = Path(file or WEBHOOK_URL_FILE)
    if not f.exists():
        return None
    try:
        return f.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None
