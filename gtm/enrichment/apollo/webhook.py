"""Apollo phone-reveal webhook receiver (stdlib only).

Apollo delivers revealed phone numbers ASYNC via an HTTP POST callback. Run this
receiver locally and expose it with a tunnel (cloudflared recommended), then set
APOLLO_WEBHOOK_URL to the tunnel URL + the webhook path.

    # terminal 1 — receiver (writes into the campaign's phone_reveals.json)
    python -m gtm webhook campaigns/spain-bricscad.yaml

    # terminal 2 — tunnel (no signup)
    cloudflared tunnel --url http://localhost:8000
    # -> https://<random>.trycloudflare.com

    # .env
    APOLLO_WEBHOOK_URL=https://<random>.trycloudflare.com/apollo-webhook

Callbacks update the same PhoneRevealStore the enrich runner reads, keyed by
apollo_id, so `merge_phones` works identically whether numbers arrive by webhook
or by polling.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .phones import PhoneRevealStore

# Serialize read-modify-write across the ThreadingHTTPServer worker threads.
_STORE_LOCK = threading.Lock()


def _phone_numbers(record: dict) -> list[str]:
    phones: list[str] = []
    for container in (record, record.get("person"), record.get("contact")):
        if not isinstance(container, dict):
            continue
        for entry in (container.get("phone_numbers") or []):
            if isinstance(entry, dict):
                num = (entry.get("sanitized_number") or entry.get("raw_number")
                       or entry.get("number") or "").strip()
                if num and num not in phones:
                    phones.append(num)
            elif isinstance(entry, str) and entry.strip() and entry.strip() not in phones:
                phones.append(entry.strip())
    return phones


def _person_id(record: dict) -> str:
    for container in (record, record.get("person"), record.get("contact")):
        if isinstance(container, dict):
            pid = container.get("id") or container.get("person_id")
            if pid:
                return str(pid)
    return ""


def _records(payload: dict) -> list[dict]:
    people = payload.get("people")
    if isinstance(people, list) and people:
        return [{"person_id": _person_id(p), "phones": _phone_numbers(p)}
                for p in people if isinstance(p, dict)]
    return [{"person_id": _person_id(payload), "phones": _phone_numbers(payload)}]


def apply_callback(store: PhoneRevealStore, payload: dict) -> list[dict]:
    """Update the store from one Apollo callback payload. Returns the records."""
    now = datetime.now(timezone.utc).isoformat()
    credits = payload.get("credits_consumed")
    results = []
    store.reload()
    for rec in _records(payload):
        pid = rec["person_id"]
        if not pid:
            continue
        phones = rec["phones"]
        prev = store.data.get(pid) or {}
        merged = list(prev.get("phones") or [])
        for p in phones:
            if p not in merged:
                merged.append(p)
        entry = dict(prev)
        entry.update({
            "status": "done" if merged else "no_number",
            "phones": merged,
            "credits_consumed": credits,
            "received_at": now,
            "source": "webhook",
        })
        store.data[pid] = entry
        results.append({"person_id": pid, "phones": merged})
    store.save()
    return results


def make_handler(store: PhoneRevealStore, webhook_path: str):
    class WebhookHandler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path.rstrip("/") in ("", "/health"):
                store.reload()
                self._send(200, {"status": "ok", "webhook_path": webhook_path,
                                 "pending": store.pending_count(),
                                 "stored": len(store.data)})
            else:
                self._send(404, {"error": "not found", "hint": "POST " + webhook_path})

        def do_POST(self):  # noqa: N802
            if self.path.rstrip("/") != webhook_path.rstrip("/"):
                self._send(404, {"error": "unknown path", "expected": webhook_path})
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send(400, {"error": "invalid json"})
                return
            with _STORE_LOCK:
                results = apply_callback(store, payload)
            for r in results:
                mark = "OK " if r["phones"] else "-- "
                print(f"  {mark}id={r['person_id']} | {', '.join(r['phones']) or 'no number'}")
            self._send(200, {"received": True, "records": results})

        def log_message(self, *_):  # silence default logging
            return

    return WebhookHandler


def run_webhook_server(store_path: str | Path, *, host: str = "0.0.0.0",
                       port: int = 8000, path: str = "/apollo-webhook") -> None:
    """Start the blocking webhook receiver, writing into `store_path`."""
    store = PhoneRevealStore(store_path)
    handler = make_handler(store, path)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Apollo webhook listening on http://{host}:{port}{path}")
    print(f"Store: {Path(store_path)}")
    print("Expose with:  cloudflared tunnel --url http://localhost:%d" % port)
    print("Then set APOLLO_WEBHOOK_URL=https://<tunnel-host>%s" % path)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping webhook receiver.")
    finally:
        server.server_close()
