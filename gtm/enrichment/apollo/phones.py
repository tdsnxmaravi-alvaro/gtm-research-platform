"""Apollo phone reveals — resumable fire + poll + merge, no webhook required.

Phone numbers are revealed ASYNC. This module fires reveal requests for
contacts that have an apollo_id but no direct phone, persists each request so
it is never re-fired (avoids double charging), and polls webhook_result to
recover numbers without depending on the local webhook receiver.

State lives in a single JSON file keyed by apollo_id:
    {apollo_id: {status, request_id, phones, fired_at, received_at}}
    status: pending | done | no_number
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .client import ApolloClient
from ..models import EnrichedContact


class PhoneRevealStore:
    """Resumable per-apollo_id phone-reveal state, persisted atomically."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: dict = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(self.path)

    def is_attempted(self, apollo_id: str) -> bool:
        return apollo_id in self.data

    def phones_for(self, apollo_id: str) -> list[str]:
        return (self.data.get(apollo_id) or {}).get("phones") or []

    def status_for(self, apollo_id: str) -> str:
        return (self.data.get(apollo_id) or {}).get("status", "")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fire_reveals(
    client: ApolloClient,
    contacts: list[EnrichedContact],
    store: PhoneRevealStore,
    *,
    max_reveals: int | None = None,
    delay: float = 0.4,
) -> int:
    """Fire reveals for contacts lacking a phone and not already attempted.

    Returns the number of requests fired.
    """
    targets = [
        c for c in contacts
        if c.apollo_id and not c.direct_phone and not store.is_attempted(c.apollo_id)
    ]
    if max_reveals:
        targets = targets[:max_reveals]

    fired = 0
    for i, c in enumerate(targets, 1):
        try:
            status, request_id = client.fire_phone_reveal(c.apollo_id)
        except Exception as exc:  # noqa: BLE001 - record & continue
            store.data[c.apollo_id] = {"status": "error", "error": str(exc),
                                        "fired_at": _now()}
            continue
        store.data[c.apollo_id] = {
            "status": "pending" if status == 200 else "error",
            "request_id": request_id,
            "http_status": status,
            "company": c.company,
            "name": c.contact_name,
            "phones": [],
            "fired_at": _now(),
        }
        if status == 200:
            fired += 1
        if i % 25 == 0:
            store.save()
        if status in (401, 403):
            break
        time.sleep(delay)
    store.save()
    return fired


def poll_reveals(
    client: ApolloClient,
    store: PhoneRevealStore,
    *,
    max_calls: int = 380,
    delay: float = 0.2,
) -> tuple[int, int, int]:
    """One polling pass. Returns (resolved, no_number, still_pending)."""
    resolved = no_number = pending = calls = 0
    for apollo_id, rec in store.data.items():
        if rec.get("status") in ("done", "no_number"):
            continue
        request_id = rec.get("request_id")
        if not request_id:
            pending += 1
            continue
        if calls >= max_calls:
            pending += 1
            continue
        try:
            code, phones = client.get_phone_result(request_id)
        except Exception:  # noqa: BLE001
            pending += 1
            continue
        calls += 1
        if code == 200 and phones:
            rec["phones"] = phones
            rec["status"] = "done"
            rec["received_at"] = _now()
            resolved += 1
        elif code == 200:
            rec["status"] = "no_number"
            rec["received_at"] = _now()
            no_number += 1
        else:  # 404 not ready, 429 rate limited, etc.
            pending += 1
            if code == 429:
                break
        time.sleep(delay)
    store.save()
    return resolved, no_number, pending


def merge_phones(contacts: list[EnrichedContact], store: PhoneRevealStore) -> int:
    """Fill direct_phone + phone_reveal_status on contacts from the store."""
    filled = 0
    for c in contacts:
        if not c.apollo_id:
            continue
        status = store.status_for(c.apollo_id)
        if status:
            c.phone_reveal_status = "found" if status == "done" else status
        phones = store.phones_for(c.apollo_id)
        if phones and not c.direct_phone:
            c.direct_phone = ", ".join(phones)
            filled += 1
    return filled
