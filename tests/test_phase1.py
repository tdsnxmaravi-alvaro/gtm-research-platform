"""Tests for Phase 1: prompt builder, ingest parser, scoring URL gate."""

from gtm.config import CampaignConfig
from gtm.prompts import build_prompt, format_companies
from gtm.ingest import parse_results, normalize_result, load_provided_list
from gtm.scoring import score_results, tier_from_score, apply_url_gate


def _cfg(**over):
    d = dict(name="t", target_type="resellers", mode="provided", country="Spain",
             products=[{"name": "BricsCAD", "value_prop": "vp",
                        "fit_criteria": ["sells CAD"]}],
             provided_list_path="x.csv")
    d.update(over)
    return CampaignConfig(**d)


# --- prompt builder ------------------------------------------------------- #
def test_prompt_contains_key_parts():
    c = _cfg()
    p = build_prompt(c, c.products[0], company_input=format_companies([{"company": "Acme"}]))
    assert "BricsCAD" in p and "Spain" in p
    assert "Acme" in p
    assert "cannot exceed tier C" in p.lower() or "exceed tier C" in p
    assert '"results"' in p


def test_prompt_vertical_variant():
    c = _cfg(mode="discover", provided_list_path=None,
             verticals=[{"name": "CAM", "slug": "cam"}])
    p = build_prompt(c, c.products[0], vertical=c.verticals[0])
    assert "CAM" in p


# --- ingest --------------------------------------------------------------- #
def test_parse_results_from_fenced_json():
    text = """noise before
```json
{"results": [
  {"company": "Acme", "website": "a.es", "score": 82, "tier": "B",
   "evidence": [{"claim": "sells AutoCAD", "url": "https://a.es/partners"}],
   "recommended_products": ["BricsCAD Pro"], "notes": ""}
]}
```
after"""
    rows = parse_results(text)
    assert len(rows) == 1
    r = rows[0]
    assert r["company"] == "Acme"
    assert r["has_verified_url"] is True
    assert r["evidence_count"] == 1
    assert "https://a.es/partners" in r["evidence_urls"]


def test_normalize_result_without_evidence():
    r = normalize_result({"company": "X", "score": 50, "tier": "C"})
    assert r["has_verified_url"] is False
    assert r["evidence_count"] == 0


def test_normalize_result_sums_dimension_scores():
    r = normalize_result({
        "company": "Acme", "website": "a.es",
        "dimension_scores": [
            {"name": "VAR capability", "points": 20, "max": 22,
             "rationale": "mature VAR", "evidence_url": "https://a.es/services"},
            {"name": "Adjacency", "points": 30, "max": 18,  # over max -> clamp to 18
             "rationale": "resells Autodesk", "evidence_url": "https://a.es/autodesk"},
            {"name": "Presence", "points": 10, "max": 20,
             "rationale": "regional", "evidence_url": ""},
        ],
    })
    # 20 + clamp(30->18) + 10 = 48 (total computed in Python, not from the LLM)
    assert r["score"] == 48
    assert r["evidence_count"] == 2
    assert r["has_verified_url"] is True


def test_parse_results_with_leading_bracket_noise():
    # LARA prepends [[LARA_TOOL_ACTIVITY:...]] markers before the JSON object.
    text = ('[[LARA_TOOL_ACTIVITY:eyJhIjoxfQ==]]\n\n[[LARA_TOOL_ACTIVITY:zzz]]\n'
            '{"results": [{"company": "Acme", "website": "a.es", "score": 68, '
            '"tier": "C", "evidence": [{"claim": "c", "url": "https://a.es"}]}]}')
    rows = parse_results(text)
    assert len(rows) == 1
    assert rows[0]["company"] == "Acme"
    assert rows[0]["has_verified_url"] is True


def test_load_provided_list_normalizes_headers(tmp_path):
    p = tmp_path / "list.csv"
    p.write_text("Company Name,URL\nAcme,https://a.es\n,skip\n", encoding="utf-8")
    rows = load_provided_list(p)
    assert len(rows) == 1
    assert rows[0]["company"] == "Acme"
    assert rows[0]["website"] == "https://a.es"


def test_load_provided_list_xlsx(tmp_path):
    from openpyxl import Workbook

    p = tmp_path / "list.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["Company Name", "Website"])
    ws.append(["Acme", "https://a.es"])
    ws.append([None, None])  # blank row skipped
    wb.save(p)
    rows = load_provided_list(p)
    assert len(rows) == 1
    assert rows[0]["company"] == "Acme"
    assert rows[0]["website"] == "https://a.es"


def test_inspect_provided_list(tmp_path):
    from gtm.ingest import inspect_provided_list

    p = tmp_path / "list.csv"
    p.write_text("Reseller Name,Website,Other Software in Use\n"
                 "Acme,https://a.es,Autodesk\n"
                 "Beta,,\n"
                 "Acme,https://a.es,Autodesk\n", encoding="utf-8")
    rep = inspect_provided_list(p)
    assert rep["has_company_col"] and rep["has_website_col"]
    assert rep["with_company"] == 3
    assert rep["with_website"] == 2
    assert rep["duplicates"] == 1
    assert "other software in use" in rep["context_fields_present"]
    assert rep["ok"] is True


def test_inspect_missing_website(tmp_path):
    from gtm.ingest import inspect_provided_list

    p = tmp_path / "nolist.csv"
    p.write_text("Reseller Name\nAcme\n", encoding="utf-8")
    rep = inspect_provided_list(p)
    assert rep["has_company_col"] is True
    assert rep["has_website_col"] is False
    assert any("website" in w.lower() for w in rep["warnings"])


def test_normalize_country_expands_codes():
    from gtm.config import normalize_country

    assert normalize_country("DE") == "Germany"
    assert normalize_country("de") == "Germany"
    assert normalize_country("ESP") == "Spain"
    assert normalize_country("US") == "United States"
    assert normalize_country("UK") == "United Kingdom"  # common non-ISO alias
    # Full names and multi-country strings pass through unchanged.
    assert normalize_country("Germany") == "Germany"
    assert normalize_country("Spain and Portugal") == "Spain and Portugal"
    assert normalize_country("") == ""


def test_load_provided_list_normalizes_country_codes(tmp_path):
    p = tmp_path / "list.csv"
    p.write_text("Company Name,Website,Country\nAcme,https://a.de,DE\n",
                 encoding="utf-8")
    rows = load_provided_list(p)
    assert rows[0]["country"] == "Germany"


def test_inspect_warns_on_country_codes(tmp_path):
    from gtm.ingest import inspect_provided_list

    p = tmp_path / "list.csv"
    p.write_text("Company Name,Website,Country\nAcme,https://a.de,DE\n",
                 encoding="utf-8")
    rep = inspect_provided_list(p)
    assert any("code" in w.lower() and "Germany" in w for w in rep["warnings"])



def test_schema_ai_excludes_pii_samples():
    from gtm.ingest.schema_ai import _safe_samples

    headers = ["Razon Social", "E-Mail Address", "Contact Telephone Number", "Sitio Web"]
    rows = [{"Razon Social": "Acme", "E-Mail Address": "a@a.es",
             "Contact Telephone Number": "600123123", "Sitio Web": "https://a.es"}]
    samples = _safe_samples(headers, rows)
    assert "Razon Social" in samples and "Sitio Web" in samples
    # PII columns must NOT be sampled
    assert "E-Mail Address" not in samples
    assert "Contact Telephone Number" not in samples


def test_schema_ai_map_and_overrides(monkeypatch):
    from gtm.ingest import schema_ai

    class _FakeSchemaProvider:
        def send(self, prompt, web_search=None):
            class R:
                text = ('{"company_column": "Razon Social", "website_column": "Sitio Web", '
                        '"country_column": "", "context_columns": ["Sector"], '
                        '"warnings": ["ok"]}')
            return R()

    monkeypatch.setattr(schema_ai, "_build_provider", lambda: _FakeSchemaProvider())
    mapping = schema_ai.ai_map_columns(["Razon Social", "Sitio Web", "Sector"], [])
    assert mapping["company_column"] == "Razon Social"
    ov = schema_ai.overrides_from_ai(mapping)
    assert ov["razon social"] == "company"
    assert ov["sitio web"] == "website"


def test_schema_ai_parses_single_quoted_output(monkeypatch):
    # Some models return a Python-style dict (single quotes) instead of JSON.
    from gtm.ingest import schema_ai

    class _FakeSchemaProvider:
        def send(self, prompt, web_search=None):
            class R:
                text = ("{'company_column': 'Reseller Name', 'website_column': 'Website', "
                        "'country_column': 'End Customer Country', 'context_columns': ['Size'], "
                        "'warnings': [\"contains misspelled 'Lagre'\"]}")
            return R()

    monkeypatch.setattr(schema_ai, "_build_provider", lambda: _FakeSchemaProvider())
    mapping = schema_ai.ai_map_columns(["Reseller Name", "Website"], [])
    assert mapping is not None
    assert mapping["company_column"] == "Reseller Name"
    assert mapping["website_column"] == "Website"


def test_load_provided_list_with_ai_overrides(tmp_path):
    p = tmp_path / "weird.csv"
    p.write_text("Razon Social,Sitio Web\nAcme,https://a.es\n", encoding="utf-8")
    rows = load_provided_list(p, column_overrides={"razon social": "company",
                                                   "sitio web": "website"})
    assert len(rows) == 1
    assert rows[0]["company"] == "Acme"
    assert rows[0]["website"] == "https://a.es"


# --- scoring URL gate ----------------------------------------------------- #
def test_tier_from_score():
    c = _cfg()
    assert tier_from_score(c, 90) == "A"
    assert tier_from_score(c, 72) == "B"
    assert tier_from_score(c, 55) == "C"
    assert tier_from_score(c, 10) == "D"


def test_url_gate_caps_without_evidence():
    c = _cfg()  # unverified_tier_cap defaults to C
    r = apply_url_gate(c, {"tier": "A", "score": 90, "has_verified_url": False})
    assert r["final_tier"] == "C"
    assert r["tier_capped"] is True


def test_url_gate_keeps_with_evidence():
    c = _cfg()
    r = apply_url_gate(c, {"tier": "A", "score": 90, "has_verified_url": True})
    assert r["final_tier"] == "A"
    assert r["tier_capped"] is False


def test_score_results_batch():
    c = _cfg()
    out = score_results(c, [
        {"tier": "A", "score": 90, "has_verified_url": True},
        {"tier": "B", "score": 75, "has_verified_url": False},
    ])
    assert out[0]["final_tier"] == "A"
    assert out[1]["final_tier"] == "C"  # capped


def test_discover_gate_ignores_negated_competitor():
    from gtm.scoring.engine import apply_exclusion_gates
    c = CampaignConfig(
        name="t", target_type="resellers", mode="discover", country="Spain",
        vendor="Trimble",
        products=[{"name": "Trimble", "value_prop": "vp", "fit_criteria": ["x"]}],
    )
    r = apply_exclusion_gates(c, {
        "tier": "A", "final_tier": "A", "score": 90, "has_verified_url": True,
        "notes": "not an Autodesk Gold partner; independent VAR",
        "software_resold": "", "fit_summary": "",
    })
    assert r["final_tier"] == "A"
    assert not r.get("tier_capped")

    locked = apply_exclusion_gates(c, {
        "tier": "A", "final_tier": "A", "score": 90, "has_verified_url": True,
        "notes": "Autodesk Gold partner",
        "software_resold": "", "fit_summary": "",
    })
    assert locked["final_tier"] == "D"
    assert locked["tier_capped"] is True


def test_aggregate_passes_averages_scores():
    from gtm.research.runner import _aggregate_passes

    passA = [{"company": "Acme", "score": 80, "evidence_urls": "https://a.es/1"}]
    passB = [{"company": "Acme", "score": 70, "evidence_urls": "https://a.es/2"}]
    passC = [{"company": "Acme", "score": 72, "evidence_urls": "https://a.es/1"}]
    out = _aggregate_passes([passA, passB, passC])
    assert len(out) == 1
    assert out[0]["score"] == 74  # round(mean(80,70,72))
    assert out[0]["passes"] == 3
    # evidence URLs unioned across passes
    assert out[0]["evidence_count"] == 2
    assert out[0]["has_verified_url"] is True


def test_ensemble_run_batch_averages_across_providers(tmp_path):
    from gtm.research.runner import _run_batch

    def _resp(score):
        class R:
            text = ('{"results":[{"company":"Acme","website":"a.es","score":%d,'
                    '"tier":"B","evidence":[{"claim":"x","url":"https://a.es"}]}]}' % score)
        return R()

    class _Prov:
        def __init__(self, name, score):
            self.name = name
            self._s = score

        def send(self, prompt, web_search=None):
            return _resp(self._s)

    c = _cfg()
    providers = [_Prov("lara", 80), _Prov("azure-sol", 60)]
    out = _run_batch(c, providers, "prompt", tmp_path, "batch1", passes=1, delay=0)
    assert len(out) == 1
    # mean(80, 60) = 70, +5 agreement bonus (2 providers found it) -> 75
    assert out[0]["score"] == 75
    assert out[0]["passes"] == 2
    assert out[0]["ensemble_agreement"] == 2
    assert out[0]["ensemble_singleton"] is False
    assert out[0]["ensemble_providers"] == "azure-sol,lara"  # sorted, both models


def test_ensemble_singleton_is_flagged_and_penalized(tmp_path):
    from gtm.research.runner import _run_batch

    class _Prov:
        def __init__(self, name, company, score):
            self.name = name
            self._c = company
            self._s = score

        def send(self, prompt, web_search=None):
            class R:
                text = ('{"results":[{"company":"%s","website":"x.es","score":%d,'
                        '"tier":"B","evidence":[{"claim":"x","url":"https://x.es"}]}]}'
                        % (self._c, self._s))
            return R()

    c = _cfg()
    # Each provider surfaces a DIFFERENT company -> both are singletons.
    providers = [_Prov("lara", "Acme", 80), _Prov("azure-sol", "Globex", 80)]
    out = _run_batch(c, providers, "prompt", tmp_path, "batch1", passes=1, delay=0)
    by = {r["company"].lower(): r for r in out}
    assert by["acme"]["ensemble_agreement"] == 1
    assert by["acme"]["ensemble_singleton"] is True
    assert by["acme"]["score"] == 75  # 80 - 5 singleton penalty
    assert by["globex"]["ensemble_singleton"] is True


def test_azure_foundry_parses_responses_payload():
    from gtm.providers.azure_foundry import _extract_text, _annotation_urls

    payload = {
        "output": [
            {"type": "web_search_call"},
            {"type": "message", "content": [
                {"type": "output_text", "text": "Acme sells CAD.",
                 "annotations": [{"url": "https://acme.example/about"}]},
            ]},
        ]
    }
    assert _extract_text(payload) == "Acme sells CAD."
    assert _annotation_urls(payload) == ["https://acme.example/about"]
    # SDK convenience field wins when present.
    assert _extract_text({"output_text": "hi", "output": []}) == "hi"


def test_run_batch_retries_transient_provider_error(tmp_path, monkeypatch):
    from gtm.research.runner import _run_batch

    class _Flaky:
        name = "azure-sol"

        def __init__(self):
            self.calls = 0

        def send(self, prompt, web_search=None):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("HTTP 429")  # transient — should be retried

            class R:
                text = ('{"results":[{"company":"Acme","website":"a.es","score":80,'
                        '"tier":"B","evidence":[{"claim":"x","url":"https://a.es"}]}]}')
            return R()

    monkeypatch.setattr("gtm.research.runner.time.sleep", lambda *_: None)
    prov = _Flaky()
    out = _run_batch(_cfg(research_retries=2), [prov], "prompt", tmp_path, "t",
                     passes=1, delay=0)
    assert prov.calls == 3          # failed twice, succeeded on the 3rd
    assert len(out) == 1 and out[0]["company"] == "Acme"


def test_run_batch_records_per_provider_counts(tmp_path, monkeypatch):
    from gtm.research.runner import _run_batch

    def _prov(name, companies):
        class P:
            def send(self, prompt, web_search=None):
                res = ",".join(f'{{"company":"{c}","website":"{c}.es","score":80,'
                               f'"tier":"B","evidence":[{{"claim":"x","url":"https://{c}.es"}}]}}'
                               for c in companies)
                class R:
                    text = '{"results":[' + res + ']}'
                return R()
        p = P()
        p.name = name
        return p

    monkeypatch.setattr("gtm.research.runner.time.sleep", lambda *_: None)
    stats = {}
    _run_batch(_cfg(), [_prov("lara", ["Acme", "Globex"]), _prov("azure-sol", ["Acme"])],
               "prompt", tmp_path, "t", passes=1, delay=0, provider_stats=stats)
    assert len(stats["lara"]) == 2
    assert len(stats["azure-sol"]) == 1


def test_factory_resolves_inline_endpoint_url(monkeypatch):
    from gtm.config.schema import LLMProvider, ProviderType
    from gtm.providers import build_provider

    monkeypatch.setenv("FOUNDRY_TEST_KEY", "secret")
    cfg = LLMProvider(name="gpt-next", type=ProviderType.azure_foundry,
                      model="gpt-next", endpoint_url="https://x.ai/openai/v1",
                      api_key_env="FOUNDRY_TEST_KEY", web_search=True)
    prov = build_provider(cfg, load_env=False)
    assert prov.endpoint == "https://x.ai/openai/v1"
    assert prov.deployment == "gpt-next"
    assert prov.web_search is True



