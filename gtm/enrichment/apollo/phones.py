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
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .client import ApolloClient
from ..models import EnrichedContact


# One lock PER store file, shared across all PhoneRevealStore instances in this
# process, so the runner (fire_reveals) and the webhook receiver never write the
# same phone_reveals.json concurrently (Windows: os.replace -> PermissionError).
_LOCKS_META = threading.Lock()
_PATH_LOCKS: dict[str, threading.Lock] = {}


def _lock_for(path) -> threading.Lock:
    key = str(Path(path).resolve()).lower()
    with _LOCKS_META:
        lk = _PATH_LOCKS.get(key)
        if lk is None:
            lk = threading.Lock()
            _PATH_LOCKS[key] = lk
        return lk


# Status precedence so a merge never downgrades a resolved reveal.
_STATUS_RANK = {"done": 3, "no_number": 2, "pending": 1, "error": 0, "": 0}


def _merge_entry(a: dict, b: dict) -> dict:
    """Merge two records for the same apollo_id: keep the more-advanced status and
    union the phone numbers (so concurrent writers never lose a delivered number)."""
    hi, lo = (a, b) if _STATUS_RANK.get(a.get("status", ""), 0) >= \
        _STATUS_RANK.get(b.get("status", ""), 0) else (b, a)
    merged = dict(lo)
    merged.update(hi)  # advanced-status fields win
    phones: list[str] = []
    for src in (a, b):
        for p in (src.get("phones") or []):
            if p and p not in phones:
                phones.append(p)
    if phones:
        merged["phones"] = phones
    return merged


def _merge_stores(disk: dict, mem: dict) -> dict:
    """Union two store dicts by apollo_id, merging conflicting entries."""
    out = dict(disk)
    for k, v in mem.items():
        out[k] = _merge_entry(disk[k], v) if k in disk else v
    return out


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

    def reload(self) -> None:
        """Re-read the store from disk (used while a webhook writes to it)."""
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        # Serialize all writers to this file (runner + webhook receiver) so the
        # atomic replace never collides on Windows.
        with _lock_for(self.path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Merge with whatever is on disk before writing, so a concurrent writer
            # (e.g. the webhook receiver persisting a delivered number) is never lost.
            self.data = _merge_stores(self._read_disk(), self.data)
            payload = json.dumps(self.data, indent=2, ensure_ascii=False)
            tmp = self.path.with_name(f"{self.path.name}.{time.time_ns()}.tmp")
            try:
                tmp.write_text(payload, encoding="utf-8")
            except OSError:
                return  # can't even stage a temp file; keep in-memory state
            # os.replace can transiently fail on Windows if another process/AV holds
            # the target; retry with backoff before a best-effort direct write.
            last_exc: Exception | None = None
            for attempt in range(10):
                try:
                    tmp.replace(self.path)
                    return
                except PermissionError as exc:
                    last_exc = exc
                    time.sleep(0.1 * (attempt + 1))
            # Fallback: write in place (also guarded — never crash the caller).
            try:
                self.path.write_text(payload, encoding="utf-8")
            except OSError:
                print(f"  !! could not persist {self.path.name} "
                      f"({last_exc}); keeping in-memory state")
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass

    def _read_disk(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def is_attempted(self, apollo_id: str) -> bool:
        return apollo_id in self.data

    def phones_for(self, apollo_id: str) -> list[str]:
        return (self.data.get(apollo_id) or {}).get("phones") or []

    def status_for(self, apollo_id: str) -> str:
        return (self.data.get(apollo_id) or {}).get("status", "")

    def pending_count(self) -> int:
        return sum(1 for r in self.data.values()
                   if r.get("status") not in ("done", "no_number"))


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
    for c in targets:
        try:
            status, request_id = client.fire_phone_reveal(c.apollo_id)
        except Exception as exc:  # noqa: BLE001 - record & continue
            # Persist the failed attempt immediately: an ambiguous network error
            # may have reached (and charged) Apollo, so we never blindly re-fire.
            store.data[c.apollo_id] = {"status": "error", "error": str(exc),
                                        "fired_at": _now()}
            store.save()
            continue
        if status in (401, 402, 403):
            # Credit/auth failure: do NOT mark attempted, so the reveal retries
            # after credits are topped up. Stop this pass (resumable).
            print("  !! Apollo credit/auth error on phone reveal — stopping (resumable).")
            break
        store.data[c.apollo_id] = {
            "status": "pending" if status == 200 else "error",
            "request_id": request_id,
            "http_status": status,
            "company": c.company,
            "name": c.contact_name,
            "phones": [],
            "fired_at": _now(),
        }
        # Save BEFORE the next fire so a crash can never re-charge this apollo_id.
        store.save()
        if status == 200:
            fired += 1
        if status == 429:  # rate limited — resumable, stop this pass
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
