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
        self.webhook_url = webhook_url or os.getenv("APOLLO_WEBHOOK_URL")
        self.seniorities = seniorities or [
            "owner", "founder", "c_suite", "vp", "head", "director", "manager",
        ]
        self.locations = locations or []
        self.timeout = timeout
        # Real credit accounting, tallied per billable Apollo action performed.
        self.credits_used = 0
        self.usage: dict = {}  # any credit/usage headers Apollo returns
        if not self.api_key:
            raise ValueError("APOLLO_API_KEY not set (env or constructor).")

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
