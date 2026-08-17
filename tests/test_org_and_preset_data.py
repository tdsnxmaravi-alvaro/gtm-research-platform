"""#32: org/channel names from env; vendor and vertical presets from data files."""

from pathlib import Path

import yaml

from gtm.config import CampaignConfig
from gtm.prompts.vendor_presets import preset_for

DATA = Path(__file__).resolve().parents[1] / "gtm" / "prompts" / "data"


def _cfg(**over):
    d = dict(
        name="t", target_type="resellers", mode="provided", country="Spain",
        provided_list_path="x.csv",
        products=[{"name": "Trimble", "value_prop": "design sw",
                   "fit_criteria": ["sells software"]}],
    )
    d.update(over)
    return CampaignConfig(**d)


def test_vendor_presets_live_in_a_data_file():
    path = DATA / "vendor_presets.yaml"
    assert path.is_file()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "Trimble" in data
    assert data["Trimble"]["reseller_fit"]


def test_vertical_catalogue_lives_in_a_data_file():
    path = DATA / "verticals.yaml"
    assert path.is_file()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "structural-steel-detailing" in data


def test_vendor_vertical_map_lives_in_a_data_file():
    path = DATA / "vendor_verticals.yaml"
    assert path.is_file()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["Trimble"]


def test_preset_for_still_resolves_trimble():
    p = preset_for("Trimble", "resellers")
    assert p and p["value_prop"]
    assert p["fit_criteria"]


def test_org_name_defaults_and_env(monkeypatch):
    from gtm.config.org import channel_name, org_name
    monkeypatch.delenv("GTM_ORG_NAME", raising=False)
    monkeypatch.delenv("GTM_CHANNEL_NAME", raising=False)
    assert org_name() == "TD SYNNEX"
    assert channel_name() == "Datech"
    monkeypatch.setenv("GTM_ORG_NAME", "Acme Dist")
    monkeypatch.setenv("GTM_CHANNEL_NAME", "Design Hub")
    assert org_name() == "Acme Dist"
    assert channel_name() == "Design Hub"


def test_email_template_uses_org_name(monkeypatch):
    from gtm.outreach.email_gen import render_template
    monkeypatch.setenv("GTM_ORG_NAME", "Acme Dist")
    _, body = render_template(_cfg(), {"company": "Acme", "country": "Spain"})
    assert "Acme Dist" in body
    assert "TD SYNNEX" not in body


def test_research_prompt_uses_org_name(monkeypatch):
    from gtm.prompts import build_prompt
    monkeypatch.setenv("GTM_ORG_NAME", "Acme Dist")
    c = _cfg()
    out = build_prompt(c, c.products[0], company_input="1. Foo | https://foo.com")
    assert "Acme Dist" in out
    assert "for TD SYNNEX" not in out
