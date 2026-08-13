"""Apollo API client — people search, person enrichment, and async phone reveal.

Ported and generalized from the BricsCAD pipeline. Location/seniority/title
targeting is passed in from the campaign config (country-agnostic).

Secrets come from the environment: APOLLO_API_KEY and (for phone reveals)
APOLLO_WEBHOOK_URL.
"""

from __future__ import annotations

import os

import requests

_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/api_search"
_ORG_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_companies/search"
_MATCH_URL = "https://api.apollo.io/api/v1/people/match"
_WEBHOOK_RESULT_URL = "https://api.apollo.io/api/v1/webhook_result/{request_id}"
_PROFILE_URL = "https://api.apollo.io/api/v1/users/api_profile"
_CREDIT_USAGE_URL = "https://api.apollo.io/api/v1/usage_stats/credit_usage_stats"

# Apollo credit costs (per docs): email reveal = 1, mobile phone reveal = 8.
EMAIL_CREDIT_COST = 1
PHONE_CREDIT_COST = 8

_TITLE_PRIORITY = [
    (1, ("owner", "founder", "ceo", "president", "principal")),
    (2, ("vp", "vice president", "general manager", "managing director")),
    (3, ("director of sales", "sales director", "business development", "channel")),
    (4, ("director", "head of")),
    (5, ("manager", "sales manager", "account manager")),
]


def title_priority(title: str) -> int:
    """Lower is better; 99 = no title, 50 = has a non-priority title."""
    if not title:
        return 99
    low = title.lower()
    for priority, keywords in _TITLE_PRIORITY:
        if any(kw in low for kw in keywords):
            return priority
    return 50


def _remaining_credits(profile: dict):
    """Best-effort: pull a 'credits remaining/available' number from a variably
    shaped api_profile payload. Returns None when no such field is found."""
    best = None

    def walk(o) -> None:
        nonlocal best
        if isinstance(o, dict):
            for k, v in o.items():
                lk = str(k).lower()
                if (isinstance(v, (int, float)) and not isinstance(v, bool)
                        and "credit" in lk
                        and any(w in lk for w in ("remain", "left", "available", "balance"))):
                    best = v if best is None else min(best, v)
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(profile)
    return best


def _find_num(o, must: str, anys: tuple) -> float | None:
    """First numeric whose key contains `must` and any of `anys` (case-insensitive)."""
    out = None

    def walk(x) -> None:
        nonlocal out
        if out is not None:
            return
        if isinstance(x, dict):
            for k, v in x.items():
                lk = str(k).lower()
                if (isinstance(v, (int, float)) and not isinstance(v, bool)
                        and must in lk and any(w in lk for w in anys)):
                    out = v
                    return
                walk(v)
        elif isinstance(x, list):
            for y in x:
                walk(y)

    walk(o)
    return out


def _credit_balances(usage: dict) -> dict:
    """Map each Apollo credit type -> remaining, from credit_usage_stats. The real
    response wraps the types under a "credit_usage_stats" key:
    {"credit_usage_stats": {"lead_credit": {"limit","consumed","left_over"}, ...}}.
    lead_credit = emails/enrich, direct_dial_credit = phone reveals."""
    types = usage.get("credit_usage_stats")
    if not isinstance(types, dict):
        types = usage
    out: dict = {}
    for k, v in (types or {}).items():
        if not isinstance(v, dict):
            continue
        if "left_over" in v and isinstance(v["left_over"], (int, float)):
            out[k] = v["left_over"]
        elif isinstance(v.get("limit"), (int, float)) and isinstance(v.get("consumed"), (int, float)):
            out[k] = v["limit"] - v["consumed"]
    return out


def _credits_remaining(data: dict) -> float | None:
    """Credits left from a usage_stats/profile payload. Handles both a direct
    'remaining/left/available' field and a 'limit - used' pair. None if unknown."""
    direct = _remaining_credits(data)
    if direct is not None:
        return direct
    limit = _find_num(data, "credit", ("limit", "cap", "total", "quota", "allotted"))
    used = _find_num(data, "credit", ("used", "consumed", "spent"))
    if limit is not None and used is not None:
        return limit - used
    return None


def _published_webhook_url() -> str | None:
    """Fallback to a tunnel-published webhook URL (no manual .env editing)."""
    try:
        from .tunnel import read_webhook_url
        return read_webhook_url()
    except Exception:  # noqa: BLE001 - best effort
        return None


class ApolloClient:
    """Thin wrapper over the Apollo endpoints used by the enrichment pipeline."""

    def __init__(
        self,
        api_key: str | None = None,
        webhook_url: str | None = None,
        *,
        seniorities: list[str] | None = None,
        locations: list[str] | None = None,
        timeout: int = 60,
    ):
        self.api_key = api_key or os.getenv("APOLLO_API_KEY")
        self.webhook_url = (webhook_url or os.getenv("APOLLO_WEBHOOK_URL")
                            or _published_webhook_url())
        self.seniorities = seniorities or [
            "owner", "founder", "c_suite", "vp", "head", "director", "manager",
        ]
        self.locations = locations or []
        self.timeout = timeout
        # Real credit accounting, tallied per billable Apollo action performed.
        self.credits_used = 0
        self.usage: dict = {}  # any credit/usage headers Apollo returns
        self.exhausted = False  # set when Apollo signals out-of-credits (402/403)
        if not self.api_key:
            raise ValueError("APOLLO_API_KEY not set (env or constructor).")

    def _note_status(self, status: int) -> None:
        """Flag credit/auth exhaustion so callers can stop resumably (not burn the
        remaining companies by marking them done with no contacts)."""
        if status in (401, 402, 403):
            self.exhausted = True

    def _capture_usage(self, resp) -> None:
        """Record any credit/usage info Apollo returns in response headers."""
        try:
            for k, v in resp.headers.items():
                lk = k.lower()
                if "credit" in lk or "usage" in lk:
                    self.usage[k] = v
        except Exception:  # noqa: BLE001 - never fail on header capture
            pass

    @property
    def _headers(self) -> dict:
        return {"Content-Type": "application/json", "X-Api-Key": self.api_key}

    # -------------------------------------------------------------- preflight
    def get_api_profile(self) -> tuple[int, dict]:
        """GET /users/api_profile — used to verify the key + read the credit balance."""
        try:
            resp = requests.get(_PROFILE_URL, headers={"X-Api-Key": self.api_key},
                                timeout=self.timeout)
        except requests.RequestException:
            return 0, {}
        self._note_status(resp.status_code)
        if resp.status_code != 200:
            return resp.status_code, {}
        try:
            return 200, resp.json()
        except ValueError:
            return 200, {}

    def get_credit_usage(self) -> tuple[int, dict]:
        """GET /usage_stats/credit_usage_stats — real credit balance (best-effort;
        tries GET then POST since Apollo's method varies)."""
        for method in ("GET", "POST"):
            try:
                resp = requests.request(method, _CREDIT_USAGE_URL,
                                        headers=self._headers, timeout=self.timeout)
            except requests.RequestException:
                return 0, {}
            if resp.status_code in (404, 405):
                continue  # wrong method — try the other
            self._note_status(resp.status_code)
            if resp.status_code != 200:
                return resp.status_code, {}
            try:
                return 200, resp.json()
            except ValueError:
                return 200, {}
        return 404, {}

    def preflight(self) -> tuple[bool, str]:
        """Verify the key + credits via /usage_stats/credit_usage_stats BEFORE spending.

        Most Apollo plans are UNIFIED: one shared credit pool (reported as
        `lead_credit`) funds emails (1 credit), phone reveals (~8), and enrich — the
        per-type buckets like `direct_dial_credit` are misleading on such plans, so we
        do NOT gate phones on them. Blocks only when the key is rejected or the shared
        pool is 0. Phone spend beyond the pool is still caught in-flight (402/403).
        """
        status, usage = self.get_credit_usage()
        if status in (401, 403):
            return False, (f"Apollo key rejected (HTTP {status}) — check APOLLO_API_KEY "
                           f"and the usage_stats scope.")
        if status != 200:
            return True, f"Could not verify credits (HTTP {status}); proceeding."
        pool = _credit_balances(usage).get("lead_credit")
        if pool is not None and pool <= 0:
            self.exhausted = True
            return False, "Apollo credits exhausted (0 left) — top up before enriching."
        if pool is not None:
            return True, (f"Apollo credits: {pool} remaining "
                          f"(~{int(pool)} emails or ~{int(pool // PHONE_CREDIT_COST)} phones)")
        return True, "Apollo key valid (credit balance not reported)."

    def credit_summary(self) -> dict:
        """Remaining shared-pool credits + how many emails/phones that buys. Used by
        the UI to show capacity when Apollo is configured. 0 credits/reveal costs."""
        status, usage = self.get_credit_usage()
        if status in (401, 403):
            return {"ok": False, "error": f"key rejected (HTTP {status})"}
        if status != 200:
            return {"ok": False, "error": f"unavailable (HTTP {status})"}
        pool = _credit_balances(usage).get("lead_credit")
        cycle = usage.get("current_credit_cycle") or {} if isinstance(usage, dict) else {}
        if pool is None:
            return {"ok": True, "remaining": None}
        return {
            "ok": True,
            "remaining": int(pool),
            "emails": int(pool // EMAIL_CREDIT_COST),
            "phones": int(pool // PHONE_CREDIT_COST),
            "cycle_end": cycle.get("end_date"),
        }

    # ---------------------------------------------------------------- search
    def search_people_by_domain(self, domain: str, per_page: int = 10) -> tuple[list, int]:
        """Search decision-makers at a domain. Returns (people, total)."""
        payload = {
            "person_seniorities": self.seniorities,
            "q_organization_domains_list": [domain],
            "page": 1,
            "per_page": per_page,
            "reveal_personal_emails": True,
        }
        if self.locations:
            payload["organization_locations"] = self.locations
        resp = requests.post(_SEARCH_URL, headers=self._headers,
                             json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            self._note_status(resp.status_code)
            return [], 0
        data = resp.json()
        total = (data.get("pagination") or {}).get("total_entries", 0)
        return data.get("people", []) or [], total

    def search_org_domain(self, company_name: str) -> str | None:
        """Resolve a domain from a company name (1 credit). Best-effort."""
        payload = {"q_organization_name": company_name, "page": 1, "per_page": 3}
        if self.locations:
            payload["organization_locations"] = self.locations
        try:
            resp = requests.post(_ORG_SEARCH_URL, headers=self._headers,
                                 json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                self._note_status(resp.status_code)
                return None
            self.credits_used += 1  # org search = 1 credit
            self._capture_usage(resp)
            data = resp.json()
            orgs = data.get("organizations") or data.get("accounts") or []
            for org in orgs:
                dom = (org.get("primary_domain") or org.get("website_url") or "")
                dom = (dom.replace("https://", "").replace("http://", "")
                          .replace("www.", "").split("/")[0])
                if "." in dom and " " not in dom:
                    return dom
        except requests.RequestException:
            return None
        return None

    # --------------------------------------------------------------- enrich
    def enrich_person(self, person_id: str) -> dict | None:
        """Enrich a person by Apollo ID (reveals work/personal emails)."""
        payload = {"id": person_id, "reveal_personal_emails": True}
        try:
            resp = requests.post(_MATCH_URL, headers=self._headers,
                                 json=payload, timeout=self.timeout)
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            self._note_status(resp.status_code)
            return None
        self._capture_usage(resp)
        person = resp.json().get("person")
        if person and person.get("email"):
            self.credits_used += 1  # email reveal = 1 credit
        return person

    # ---------------------------------------------------------------- phones
    def fire_phone_reveal(self, person_id: str) -> tuple[int, str]:
        """Fire an async phone reveal. Returns (http_status, request_id).

        The number arrives later via the webhook OR is recoverable by polling
        webhook_result with the returned request_id (Apollo keeps it ~30 days).
        """
        if not self.webhook_url:
            raise ValueError("APOLLO_WEBHOOK_URL not set (required for phone reveals).")
        payload = {
            "id": person_id,
            "reveal_phone_number": True,
            "webhook_url": self.webhook_url,
        }
        resp = requests.post(_MATCH_URL, headers=self._headers,
                             json=payload, timeout=self.timeout)
        if resp.status_code == 200:
            self.credits_used += 8  # phone reveal = ~8 credits
            self._capture_usage(resp)
        else:
            self._note_status(resp.status_code)
        request_id = ""
        try:
            request_id = ((resp.json().get("phone_enrichment") or {})
                          .get("request_id", "") or "")
        except ValueError:
            pass
        return resp.status_code, request_id

    def get_phone_result(self, request_id: str) -> tuple[int, list[str]]:
        """Poll a phone-reveal result. Returns (http_status, [phones]).

        200 with phones -> resolved; 200 empty -> no number on file;
        404 -> not ready yet.
        """
        url = _WEBHOOK_RESULT_URL.format(request_id=request_id)
        resp = requests.get(url, headers={"X-Api-Key": self.api_key},
                            timeout=self.timeout)
        if resp.status_code != 200:
            return resp.status_code, []
        return 200, _phones_from_payload(resp.json())


def _phones_from_payload(payload: dict) -> list[str]:
    """Defensively pull sanitized phone numbers from a webhook_result payload."""
    people = payload.get("people")
    containers = people if isinstance(people, list) and people else [payload]
    phones: list[str] = []
    for person in containers:
        if not isinstance(person, dict):
            continue
        for entry in (person.get("phone_numbers") or []):
            if isinstance(entry, dict):
                num = (entry.get("sanitized_number") or entry.get("raw_number")
                       or entry.get("number") or "").strip()
                if num and num not in phones:
                    phones.append(num)
    return phones
