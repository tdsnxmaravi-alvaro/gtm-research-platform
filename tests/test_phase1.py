"""Tests for Phase 1: prompt builder, ingest parser, scoring URL gate."""

import json

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


def test_load_provided_list_normalizes_headers(tmp_path):
    p = tmp_path / "list.csv"
    p.write_text("Company Name,URL\nAcme,https://a.es\n,skip\n", encoding="utf-8")
    rows = load_provided_list(p)
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
