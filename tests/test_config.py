"""Tests for the campaign config schema, validation matrix, and loader."""

import pytest
from pydantic import ValidationError

from gtm.config import CampaignConfig, load_campaign


def _base(**over):
    data = dict(
        name="t", target_type="resellers", mode="provided", country="USA",
        products=[{"name": "BricsCAD"}], provided_list_path="x.csv",
    )
    data.update(over)
    return data


# --- valid combinations --------------------------------------------------- #
def test_resellers_provided_ok():
    c = CampaignConfig(**_base())
    assert c.prompt_template_key() == "resellers_provided_fit"
    assert c.language == "en"


def test_resellers_discover_vertical_ok():
    c = CampaignConfig(**_base(mode="discover", provided_list_path=None,
                               verticals=[{"name": "CAM", "slug": "cam"}]))
    assert c.prompt_template_key() == "reseller_discover_vertical"


def test_resellers_discover_broad_ok():
    c = CampaignConfig(**_base(mode="discover", provided_list_path=None))
    assert c.prompt_template_key() == "resellers_discover_broad"


def test_accounts_discover_broad_ok():
    c = CampaignConfig(**_base(target_type="accounts", mode="discover", provided_list_path=None))
    assert c.prompt_template_key() == "accounts_discover_broad"


def test_accounts_provided_ok():
    c = CampaignConfig(**_base(target_type="accounts"))
    assert c.prompt_template_key() == "accounts_provided_fit"


# --- invalid combinations ------------------------------------------------- #
def test_accounts_cannot_have_verticals():
    with pytest.raises(ValidationError):
        CampaignConfig(**_base(target_type="accounts", mode="discover",
                               provided_list_path=None,
                               verticals=[{"name": "V", "slug": "v"}]))


def test_provided_cannot_have_verticals():
    with pytest.raises(ValidationError):
        CampaignConfig(**_base(verticals=[{"name": "V", "slug": "v"}]))


def test_provided_requires_list():
    with pytest.raises(ValidationError):
        CampaignConfig(**_base(provided_list_path=None))


def test_research_provider_must_exist():
    with pytest.raises(ValidationError):
        CampaignConfig(**_base(
            llm_providers=[{"name": "lara-x", "type": "lara"}],
            research_provider="does-not-exist",
        ))


# --- derived behavior ----------------------------------------------------- #
def test_language_derived_from_country():
    c = CampaignConfig(**_base(country="Spain"))
    assert c.language == "es"
    # outreach.language stays None (= "auto") so outreach localizes per each
    # company's own country; an explicit choice would win.
    assert c.outreach.language is None


def test_credit_estimate():
    c = CampaignConfig(**_base(
        enrichment={"apollo": True, "want": "emails+phones", "max_contacts": 3},
    ))
    # 100 companies * 3 contacts * (1 email + 8 phone) = 2700
    assert c.enrichment.estimate_credits(100) == 2700


def test_credit_estimate_zero_without_apollo():
    c = CampaignConfig(**_base(enrichment={"apollo": False}))
    assert c.enrichment.estimate_credits(100) == 0


# --- loader --------------------------------------------------------------- #
def test_load_spain_example():
    c = load_campaign("campaigns/spain-bricscad.yaml")
    assert c.name == "spain-bricscad-resellers"
    assert c.target_type.value == "resellers"
    assert c.mode.value == "provided"
    assert c.language == "es"
    assert c.enrichment.estimate_credits(50) == 50 * 3 * 9
