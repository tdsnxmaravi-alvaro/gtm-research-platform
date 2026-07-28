"""Tests for Phase 2: enrichment (domains, Apollo path, LARA agent, runner).

No network: Apollo/LARA calls are replaced with in-memory stubs.
"""

from gtm.config import CampaignConfig
from gtm.config.schema import apollo_locations_for
from gtm.enrichment import (
    run_enrichment, EnrichedContact, CONTACT_COLS, extract_domain,
    enrich_company, PhoneRevealStore, merge_phones,
)
from gtm.enrichment.apollo import fire_reveals, poll_reveals
from gtm.enrichment.lara_agent.agent import _parse_contacts, enrich_company_lara


def _cfg(**over):
    d = dict(name="t2", target_type="resellers", mode="provided", country="Spain",
             products=[{"name": "BricsCAD", "value_prop": "vp",
                        "fit_criteria": ["sells CAD"]}],
             provided_list_path="x.csv")
    d.update(over)
    return CampaignConfig(**d)


# --- domains -------------------------------------------------------------- #
def test_extract_domain_variants():
    assert extract_domain("https://www.ecedesign.com/") == "ecedesign.com"
    assert extract_domain("lp360.com; geocue.com") == "lp360.com"
    assert extract_domain("unknown") == ""
    assert extract_domain("") == ""


# --- config helpers ------------------------------------------------------- #
def test_apollo_locations_from_country():
    assert apollo_locations_for("Spain") == ["Spain"]
    assert apollo_locations_for("USA") == ["United States"]
    assert apollo_locations_for("Narnia") == ["Narnia"]


def test_estimate_credits_with_phones():
    c = _cfg(enrichment={"apollo": True, "want": "emails+phones", "max_contacts": 3})
    # 4 companies * 3 contacts * (1 email + 8 phone) = 108
    assert c.enrichment.estimate_credits(4) == 108


# --- EnrichedContact ------------------------------------------------------ #
def test_contact_to_row_has_all_columns():
    c = EnrichedContact(company="Acme", domain="acme.com", email="a@acme.com")
    row = c.to_row()
    assert set(row.keys()) == set(CONTACT_COLS)
    assert row["company"] == "Acme" and row["email"] == "a@acme.com"


# --- Apollo email enrichment (stub client) -------------------------------- #
class _FakeApollo:
    def __init__(self):
        self.enriched = []

    def search_org_domain(self, name):
        return "acme.com"

    def search_people_by_domain(self, domain, per_page=10):
        return ([
            {"id": "p1", "first_name": "Ana", "last_name": "Ruiz", "title": "CEO"},
            {"id": "p2", "first_name": "Bob", "last_name": "Diaz", "title": "Manager"},
        ], 2)

    def enrich_person(self, pid):
        return {"id": pid, "name": "Ana Ruiz", "title": "CEO",
                "email": "ana@acme.com", "email_status": "verified",
                "personal_emails": [], "phone_numbers": [], "organization": {}}


def test_enrich_company_apollo(monkeypatch):
    monkeypatch.setattr("gtm.enrichment.apollo.enrich.time.sleep", lambda *_: None)
    contacts = enrich_company(_FakeApollo(), {"company": "Acme", "website": "acme.com",
                                              "final_tier": "A", "score": "90"},
                              max_contacts=2, delay=0)
    assert len(contacts) == 2
    assert contacts[0].email == "ana@acme.com"
    assert contacts[0].source == "apollo"
    # CEO sorted before Manager
    assert contacts[0].title == "CEO"


# --- phone reveal store round-trip ---------------------------------------- #
class _FakePhoneApollo:
    def fire_phone_reveal(self, pid):
        return 200, f"req-{pid}"

    def get_phone_result(self, request_id):
        return 200, ["+34123456789"]


def test_phone_reveal_flow(tmp_path, monkeypatch):
    monkeypatch.setattr("gtm.enrichment.apollo.phones.time.sleep", lambda *_: None)
    contacts = [EnrichedContact(company="Acme", apollo_id="p1")]
    store = PhoneRevealStore(tmp_path / "ph.json")
    client = _FakePhoneApollo()
    assert fire_reveals(client, contacts, store) == 1
    assert store.status_for("p1") == "pending"
    resolved, no_num, pending = poll_reveals(client, store)
    assert resolved == 1 and pending == 0
    assert merge_phones(contacts, store) == 1
    assert contacts[0].direct_phone == "+34123456789"
    assert contacts[0].phone_reveal_status == "found"
    # never re-fires an attempted contact
    assert fire_reveals(client, contacts, store) == 0


# --- LARA enrichment agent ------------------------------------------------ #
def test_lara_parse_contacts():
    text = '```json\n{"contacts":[{"contact_name":"Ana","title":"CEO",' \
           '"email":"ana@acme.com","linkedin":"","source_url":"http://x"}]}\n```'
    out = _parse_contacts(text)
    assert len(out) == 1 and out[0]["email"] == "ana@acme.com"


class _FakeLara:
    def send(self, prompt, web_search=None):
        class R:
            text = '{"contacts":[{"contact_name":"Ana","title":"CEO",' \
                   '"email":"ana@acme.com","linkedin":"http://li"}]}'
        return R()


def test_enrich_company_lara():
    contacts = enrich_company_lara(_FakeLara(),
                                   {"company": "Acme", "website": "acme.com"},
                                   country="Spain", max_contacts=3, language="es")
    assert len(contacts) == 1
    assert contacts[0].email == "ana@acme.com"
    assert contacts[0].source == "lara"


# --- runner: want=none short-circuits ------------------------------------- #
def test_run_enrichment_want_none():
    c = _cfg(enrichment={"want": "none"})
    assert run_enrichment(c, rows=[{"company": "Acme"}]) == []


def test_contact_cache_roundtrip(tmp_path):
    from gtm.enrichment import ContactCache

    cache = ContactCache(tmp_path / "c.json")
    assert cache.get("acme.com") is None
    cache.put("www.Acme.com", [EnrichedContact(company="Acme", domain="acme.com",
                                               email="a@acme.com", apollo_id="p1")])
    hit = cache.get("acme.com")  # normalized (www + case-insensitive)
    assert hit is not None and len(hit) == 1
    assert hit[0].email == "a@acme.com"
    assert "a@acme.com" in cache.known_emails()
    assert ContactCache(tmp_path / "c.json", enabled=False).get("acme.com") is None


# --- webhook callback -> store -------------------------------------------- #
def test_webhook_apply_callback(tmp_path):
    from gtm.enrichment.apollo.webhook import apply_callback

    store = PhoneRevealStore(tmp_path / "ph.json")
    store.data["p1"] = {"status": "pending", "request_id": "r1", "phones": []}
    store.save()

    payload = {"people": [{"id": "p1", "phone_numbers": [
        {"sanitized_number": "+34999888777"}]}], "credits_consumed": 8}
    results = apply_callback(store, payload)

    assert results[0]["person_id"] == "p1"
    assert store.status_for("p1") == "done"
    assert store.phones_for("p1") == ["+34999888777"]

    contacts = [EnrichedContact(company="Acme", apollo_id="p1")]
    assert merge_phones(contacts, store) == 1
    assert contacts[0].direct_phone == "+34999888777"


def test_webhook_no_number(tmp_path):
    from gtm.enrichment.apollo.webhook import apply_callback

    store = PhoneRevealStore(tmp_path / "ph.json")
    apply_callback(store, {"people": [{"id": "p2", "phone_numbers": []}]})
    assert store.status_for("p2") == "no_number"
