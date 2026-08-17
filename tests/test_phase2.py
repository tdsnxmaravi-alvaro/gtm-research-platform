"""Tests for Phase 2: enrichment (domains, Apollo path, LARA agent, runner).

No network: Apollo/LARA calls are replaced with in-memory stubs.
"""

import json

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


def test_fire_reveals_persists_after_each_fire(tmp_path, monkeypatch):
    """Crash safety: each fired reveal hits disk before the next, so a mid-run
    crash can never re-charge an already-fired apollo_id on resume."""
    monkeypatch.setattr("gtm.enrichment.apollo.phones.time.sleep", lambda *_: None)

    class _CrashAfterFirst:
        def __init__(self):
            self.calls = 0

        def fire_phone_reveal(self, pid):
            self.calls += 1
            if self.calls >= 2:
                raise RuntimeError("network down")
            return 200, f"req-{pid}"

    contacts = [EnrichedContact(company="A", apollo_id="p1"),
                EnrichedContact(company="B", apollo_id="p2")]
    path = tmp_path / "ph.json"
    store = PhoneRevealStore(path)
    fire_reveals(_CrashAfterFirst(), contacts, store)
    # A fresh store reading the SAME file sees p1 persisted (survives a crash).
    reloaded = PhoneRevealStore(path)
    assert reloaded.status_for("p1") == "pending"
    assert reloaded.is_attempted("p1")
    # p2 (the failed one) is recorded too, so it isn't blindly re-fired.
    assert reloaded.is_attempted("p2")


def test_fire_reveals_respects_max_reveals(tmp_path, monkeypatch):
    monkeypatch.setattr("gtm.enrichment.apollo.phones.time.sleep", lambda *_: None)
    contacts = [EnrichedContact(company=f"C{i}", apollo_id=f"p{i}") for i in range(5)]
    store = PhoneRevealStore(tmp_path / "ph.json")
    assert fire_reveals(_FakePhoneApollo(), contacts, store, max_reveals=3) == 3
    assert len(store.data) == 3


def test_fire_reveals_out_of_credits_is_resumable(tmp_path, monkeypatch):
    """A 402 (out of credits) must NOT mark the contact attempted, so the reveal
    retries after a top-up instead of being silently skipped forever."""
    monkeypatch.setattr("gtm.enrichment.apollo.phones.time.sleep", lambda *_: None)

    class _NoCredits:
        def fire_phone_reveal(self, pid):
            return 402, ""

    contacts = [EnrichedContact(company="A", apollo_id="p1")]
    store = PhoneRevealStore(tmp_path / "ph.json")
    assert fire_reveals(_NoCredits(), contacts, store) == 0
    assert not store.is_attempted("p1")  # retryable after credits are topped up


def test_apollo_client_flags_exhausted_on_credit_status():
    from gtm.enrichment.apollo.client import ApolloClient
    c = ApolloClient(api_key="k")
    assert c.exhausted is False
    c._note_status(404)
    assert c.exhausted is False
    c._note_status(402)
    assert c.exhausted is True


def test_remaining_credits_parser():
    from gtm.enrichment.apollo.client import _remaining_credits, _credit_balances
    assert _remaining_credits({"email_credits_remaining": 42}) == 42
    assert _remaining_credits({"a": {"credits_left": 0}}) == 0
    assert _remaining_credits({"credits_used": 100}) is None
    # Real credit_usage_stats shape: wrapped under "credit_usage_stats".
    usage = {"credit_usage_stats": {
        "lead_credit": {"limit": 4810, "consumed": 2827, "left_over": 1983},
        "direct_dial_credit": {"limit": 4000, "consumed": 4000, "left_over": 0},
    }, "current_credit_cycle": {"start_date": "x", "end_date": "y"}}
    bal = _credit_balances(usage)
    assert bal["lead_credit"] == 1983
    assert bal["direct_dial_credit"] == 0
    # Flat (unwrapped) shape also supported.
    assert _credit_balances({"lead_credit": {"left_over": 5}})["lead_credit"] == 5


def test_preflight_uses_credit_usage_stats():
    from gtm.enrichment.apollo.client import ApolloClient

    def wrap(d):
        return {"credit_usage_stats": d}
    # Shared pool (lead_credit) at 0 -> block (exhausted).
    c = ApolloClient(api_key="k")
    c.get_credit_usage = lambda: (200, wrap({"lead_credit": {"left_over": 0}}))
    ok, _ = c.preflight()
    assert ok is False and c.exhausted is True

    # Pool with credits -> ok, reports remaining + email/phone capacity.
    c2 = ApolloClient(api_key="k")
    c2.get_credit_usage = lambda: (200, wrap({"lead_credit": {"left_over": 1983}}))
    ok, msg = c2.preflight()
    assert ok is True and "1983" in msg

    # Rejected key -> block.
    c3 = ApolloClient(api_key="k")
    c3.get_credit_usage = lambda: (403, {})
    ok, msg = c3.preflight()
    assert ok is False and "rejected" in msg

    # direct_dial=0 must NOT skip phones on a unified plan (shared pool funds them).
    c4 = ApolloClient(api_key="k")
    c4.get_credit_usage = lambda: (200, wrap({"lead_credit": {"left_over": 100},
                                              "direct_dial_credit": {"left_over": 0}}))
    ok, _ = c4.preflight()
    assert ok is True

    # Unknown HTTP: fail-closed unless APOLLO_PREFLIGHT_STRICT=false.
    c5 = ApolloClient(api_key="k")
    c5.get_credit_usage = lambda: (500, {})
    ok, msg = c5.preflight()
    assert ok is False and "refusing" in msg


def test_preflight_strict_override(monkeypatch):
    from gtm.enrichment.apollo.client import ApolloClient
    monkeypatch.setenv("APOLLO_PREFLIGHT_STRICT", "false")
    c = ApolloClient(api_key="k")
    c.get_credit_usage = lambda: (500, {})
    ok, msg = c.preflight()
    assert ok is True and "proceeding" in msg


def test_credit_summary_estimates_emails_and_phones():
    from gtm.enrichment.apollo.client import ApolloClient
    c = ApolloClient(api_key="k")
    c.get_credit_usage = lambda: (200, {"credit_usage_stats": {
        "lead_credit": {"left_over": 1983}},
        "current_credit_cycle": {"end_date": "2026-09-01"}})
    s = c.credit_summary()
    assert s["ok"] and s["remaining"] == 1983
    assert s["emails"] == 1983 and s["phones"] == 247  # 1983 // 8
    assert s["cycle_end"] == "2026-09-01"


def test_tunnel_url_parsing_and_publish(tmp_path):
    from gtm.enrichment.apollo.tunnel import (
        parse_tunnel_url, publish_webhook_url, read_webhook_url,
    )
    banner = ("2026-08-13T15:34:43Z INF |  Your quick Tunnel has been created! ...  |\n"
              "2026-08-13T15:34:43Z INF |  https://represents-strictly-frank-mart."
              "trycloudflare.com                       |\n")
    url = parse_tunnel_url(banner)
    assert url == "https://represents-strictly-frank-mart.trycloudflare.com"
    assert parse_tunnel_url("no url here") is None
    f = tmp_path / "webhook_url.txt"
    full = publish_webhook_url(url, "/apollo-webhook", file=f)
    assert full.endswith("/apollo-webhook")
    assert read_webhook_url(file=f) == full


def test_apollo_client_reads_published_webhook_url(tmp_path, monkeypatch):
    monkeypatch.setenv("APOLLO_API_KEY", "k")
    monkeypatch.delenv("APOLLO_WEBHOOK_URL", raising=False)
    import gtm.enrichment.apollo.tunnel as tun
    f = tmp_path / "webhook_url.txt"
    f.write_text("https://x.trycloudflare.com/apollo-webhook", encoding="utf-8")
    monkeypatch.setattr(tun, "WEBHOOK_URL_FILE", f)
    from gtm.enrichment.apollo.client import ApolloClient
    client = ApolloClient()
    assert client.webhook_url == "https://x.trycloudflare.com/apollo-webhook"


def test_save_survives_permission_error(tmp_path, monkeypatch):
    """Windows can raise PermissionError on the atomic replace when another writer
    holds the file; save() must fall back to an in-place write, not crash the run."""
    import json
    import pathlib
    store = PhoneRevealStore(tmp_path / "ph.json")
    store.data["p1"] = {"status": "pending"}
    monkeypatch.setattr("gtm.enrichment.apollo.phones.time.sleep", lambda *_: None)
    monkeypatch.setattr(pathlib.Path, "replace",
                        lambda self, target: (_ for _ in ()).throw(PermissionError("locked")))
    store.save()  # must not raise
    assert json.load(open(tmp_path / "ph.json", encoding="utf-8"))["p1"]["status"] == "pending"


def test_store_save_merges_concurrent_writers(tmp_path):
    """Two processes writing the same store must not clobber each other: a webhook
    marking a reveal 'done' survives a later fire_reveals save from another process."""
    path = tmp_path / "ph.json"
    # Writer A (e.g. runner) fires p1 -> pending.
    a = PhoneRevealStore(path)
    a.data["p1"] = {"status": "pending", "request_id": "r1", "phones": []}
    a.save()
    # Writer B (e.g. webhook receiver) reloads, marks p1 done with a number.
    b = PhoneRevealStore(path)
    b.data["p1"] = {"status": "done", "phones": ["+34123"]}
    b.save()
    # Writer A, still holding a STALE in-memory p1 (pending), now fires p2 and saves.
    a.data["p2"] = {"status": "pending", "request_id": "r2", "phones": []}
    a.save()
    # The delivered number must survive; p2 must be added.
    final = PhoneRevealStore(path)
    assert final.status_for("p1") == "done"
    assert final.phones_for("p1") == ["+34123"]
    assert final.is_attempted("p2")


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


def test_fire_reveals_retryable_http_not_attempted(tmp_path, monkeypatch):
    monkeypatch.setattr("gtm.enrichment.apollo.phones.time.sleep", lambda *_: None)

    class _Transient:
        def fire_phone_reveal(self, pid):
            return 503, ""

    contacts = [EnrichedContact(company="A", apollo_id="p1")]
    store = PhoneRevealStore(tmp_path / "ph.json")
    assert fire_reveals(_Transient(), contacts, store) == 0
    assert not store.is_attempted("p1")


def test_run_enrichment_persists_contacts_when_exhausted(tmp_path, monkeypatch):
    """Billed contacts must hit disk even if Apollo flags exhausted mid-company."""
    billed = [EnrichedContact(company="Acme", domain="acme.com",
                              email="a@acme.com", source="apollo")]

    class _Client:
        exhausted = False
        credits_used = 1
        usage = {}

        def preflight(self):
            return True, "ok"

    client = _Client()

    def _enrich(_c, _row, max_contacts=3, delay=0.5):
        client.exhausted = True
        return billed

    monkeypatch.setattr("gtm.enrichment.runner.enrich_company", _enrich)
    monkeypatch.setattr("gtm.enrichment.runner.ApolloClient", lambda **_kw: client)

    out = tmp_path / "camp"
    out.mkdir()
    rows = [
        {"company": "Acme", "website": "https://acme.com", "final_tier": "A", "score": "90"},
        {"company": "Beta", "website": "https://beta.com", "final_tier": "A", "score": "88"},
    ]
    c = _cfg(enrichment={"provider": "apollo", "want": "emails", "max_contacts": 3})
    got = run_enrichment(c, rows=rows, out_dir=out, use_cache=True, resume=False, delay=0)
    assert len(got) == 1
    assert got[0].email == "a@acme.com"
    csv_text = (out / "contacts.csv").read_text(encoding="utf-8")
    assert "a@acme.com" in csv_text
    state = json.loads((out / "enrich_state.json").read_text(encoding="utf-8"))
    assert "Acme" in state["done"]
    assert "Beta" not in state["done"]
    from gtm.enrichment.cache import ContactCache
    cached = ContactCache(path=out.parent / ".gtm_cache" / "contacts.json").get("acme.com")
    assert cached and cached[0].email == "a@acme.com"


def test_run_enrichment_checkpoint_flushes_complete_csv(tmp_path, monkeypatch):
    """Cache-hit path may skip intermediate CSV rewrites; the file is complete at end."""
    monkeypatch.setenv("GTM_CSV_CHECKPOINT_EVERY", "50")

    class _Client:
        exhausted = False
        credits_used = 0
        usage = {}

        def preflight(self):
            return True, "ok"

    monkeypatch.setattr("gtm.enrichment.runner.ApolloClient", lambda **_kw: _Client())
    from gtm.enrichment.cache import ContactCache

    out = tmp_path / "camp"
    out.mkdir()
    cache = ContactCache(path=out.parent / ".gtm_cache" / "contacts.json")
    for name, domain in (("Acme", "acme.com"), ("Beta", "beta.com"), ("Gamma", "gamma.com")):
        cache.put(domain, [EnrichedContact(
            company=name, domain=domain, email=f"a@{domain}", source="apollo")])
    rows = [
        {"company": "Acme", "website": "https://acme.com", "final_tier": "A", "score": "90"},
        {"company": "Beta", "website": "https://beta.com", "final_tier": "A", "score": "88"},
        {"company": "Gamma", "website": "https://gamma.com", "final_tier": "A", "score": "87"},
    ]
    c = _cfg(enrichment={"provider": "apollo", "want": "emails", "max_contacts": 3})
    got = run_enrichment(c, rows=rows, out_dir=out, use_cache=True, resume=False, delay=0)
    assert {c.email for c in got} == {"a@acme.com", "a@beta.com", "a@gamma.com"}
    csv_text = (out / "contacts.csv").read_text(encoding="utf-8")
    assert "a@acme.com" in csv_text and "a@beta.com" in csv_text and "a@gamma.com" in csv_text
