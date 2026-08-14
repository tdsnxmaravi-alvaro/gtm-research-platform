"""Tests for discover-mode prompt builder + scoring gates (issue #15)."""

from gtm.config import CampaignConfig
from gtm.config.schema import Vertical
from gtm.prompts import build_prompt, discover_verticals
from gtm.scoring import score_results


def _discover_cfg(vendor="Trimble", verticals=None, **over):
    d = dict(
        name="disc", target_type="resellers", mode="discover", country="USA",
        vendor=vendor,
        products=[{"name": "Trimble", "value_prop": "field/AEC software",
                   "fit_criteria": ["sells design software"]}],
        verticals=verticals if verticals is not None else [],
    )
    d.update(over)
    return CampaignConfig(**d)


# --- discover_verticals helper ------------------------------------------- #
def test_discover_verticals_default_core_secondary():
    vs = discover_verticals("Trimble")
    assert vs and all(v["slug"] and v["name"] and v["focus"] for v in vs)
    assert all(isinstance(v["example_software"], list) and v["example_software"] for v in vs)


def test_discover_verticals_slug_filter():
    vs = discover_verticals("Trimble", slugs=["structural-steel-detailing"])
    assert len(vs) == 1
    assert vs[0]["slug"] == "structural-steel-detailing"


def test_discover_verticals_are_vertical_constructible():
    for v in discover_verticals("Bricsys"):
        obj = Vertical(**v)
        assert obj.example_software == v["example_software"]


# --- prompt builder ------------------------------------------------------ #
def test_discover_vertical_prompt_is_exhaustive():
    v = discover_verticals("Trimble", slugs=["structural-steel-detailing"])[0]
    c = _discover_cfg(verticals=[v])
    p = build_prompt(c, c.products[0], vertical=c.verticals[0])
    # vendor + vertical + product context
    assert "Trimble" in p and v["name"] in p and "USA" in p
    # vendor landscape (example software brands) present
    assert any(sw.split()[0] in p for sw in v["example_software"])
    # exclusions rendered with competitor + level
    assert "Autodesk Gold/Platinum/Premier partners" in p
    # discovery rules + two-part task + independence emphasis
    assert "PART 1" in p and "PART 2" in p and "Independence FIRST" in p
    # product vendors / owners are explicitly excluded (only resellers wanted)
    assert "EXCLUDE VENDORS" in p
    # strict JSON output schema
    assert '"results"' in p


def test_draftsight_prompt_excludes_autodesk_not_dassault():
    v = discover_verticals("DraftSight", slugs=["solidworks-vars"])[0]
    c = _discover_cfg(vendor="DraftSight",
                      products=[{"name": "DraftSight", "value_prop": "2D CAD"}],
                      verticals=[v])
    p = build_prompt(c, c.products[0], vertical=c.verticals[0])
    assert "Autodesk Gold/Platinum partners" in p
    assert "locked to Dassault" not in p and "SOLIDWORKS-locked" not in p


# --- scoring gates ------------------------------------------------------- #
def _row(**over):
    r = {"company": "Acme", "website": "https://acme.example", "score": 90,
         "tier": "A", "has_verified_url": True, "independence": "Independent",
         "software_resold": "", "notes": "", "fit_summary": ""}
    r.update(over)
    return r


def test_independent_high_score_stays_a():
    c = _discover_cfg()
    out = score_results(c, [_row()])
    assert out[0]["final_tier"] == "A"


def test_captive_reseller_capped_at_c():
    c = _discover_cfg()
    out = score_results(c, [_row(independence="Subsidiary")])
    assert out[0]["final_tier"] == "C"
    assert out[0]["tier_capped"] and "non-independent" in out[0]["tier_cap_reason"]


def test_locked_competitor_partner_capped_at_d():
    c = _discover_cfg()  # Trimble excludes Autodesk Gold/Platinum/Premier
    out = score_results(c, [_row(software_resold="Autodesk AutoCAD (Gold Partner)")])
    assert out[0]["final_tier"] == "D"
    assert "Autodesk-locked partner" in out[0]["tier_cap_reason"]


def test_exclusive_lock_detected():
    v = discover_verticals("Newforma", slugs=["autodesk-aec-vars"])
    c = _discover_cfg(vendor="Newforma",
                      products=[{"name": "Newforma", "value_prop": "PIM"}],
                      verticals=v)
    out = score_results(c, [_row(notes="Bentley ProjectWise exclusive reseller")])
    assert out[0]["final_tier"] == "D"


def test_gates_do_not_apply_in_provided_mode():
    c = CampaignConfig(name="prov", target_type="resellers", mode="provided",
                       country="USA", vendor="Trimble", provided_list_path="x.csv",
                       products=[{"name": "Trimble", "value_prop": "vp"}])
    out = score_results(c, [_row(independence="Subsidiary",
                                 software_resold="Autodesk Gold Partner")])
    assert out[0]["final_tier"] == "A"  # discover gates skipped


# --- multi-country discover (Phase D) ------------------------------------ #
def test_datech_countries_constant():
    from gtm.config.schema import DATECH_COUNTRIES
    assert set(DATECH_COUNTRIES) == {"North America", "Caribbean & Central America", "EMEA", "APJ"}
    flat = [c for lst in DATECH_COUNTRIES.values() for c in lst]
    assert len(flat) == len(set(flat))  # no duplicate countries across regions
    assert "United States" in DATECH_COUNTRIES["North America"]
    assert "Hong Kong" in DATECH_COUNTRIES["APJ"]


def test_countries_anchors_country_and_language():
    v = discover_verticals("Trimble", slugs=["structural-steel-detailing"])[0]
    c = _discover_cfg(country="", countries=["United States", "Canada"], verticals=[v])
    assert c.country == "United States"  # anchored to first
    assert c.language == "en"


def test_build_prompt_country_override():
    v = discover_verticals("Trimble", slugs=["structural-steel-detailing"])[0]
    c = _discover_cfg(countries=["United States", "Canada"], verticals=[v])
    p = build_prompt(c, c.products[0], vertical=c.verticals[0], country="Canada")
    assert "Canada" in p


class _FakeProvider:
    name = "fake"

    def __init__(self):
        self.prompts = []

    def send(self, prompt):
        import types
        self.prompts.append(prompt)
        return types.SimpleNamespace(
            text='{"results":[{"company":"Acme","website":"https://a.com","dimension_scores":[]}]}')


def test_discover_runs_one_pass_per_country(tmp_path):
    from gtm.research.runner import run_campaign
    v = discover_verticals("Trimble", slugs=["structural-steel-detailing"])[0]
    c = _discover_cfg(country="", countries=["United States", "Canada"], verticals=[v])
    fake = _FakeProvider()
    rows = run_campaign(c, provider=fake, out_dir=tmp_path, delay=0, resume=False)
    assert len(fake.prompts) == 2  # one pass per country (1 vertical x 1 product)
    assert {r["country"] for r in rows} == {"United States", "Canada"}
    assert any("United States" in p for p in fake.prompts)
    assert any("Canada" in p for p in fake.prompts)
