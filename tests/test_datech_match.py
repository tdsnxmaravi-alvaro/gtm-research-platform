"""Tests for the Datech reseller matcher (net-new vs existing partner flag)."""

from gtm.consolidate.datech_match import (
    DatechIndex, load_datech_names, match_companies, normalize_for_match,
)

DATECH = [
    "ACME CAD SOLUTIONS INC",
    "365 IT SOLUTIONS/1583628 ONTARIO INC.",
    "Redshift Reprographics LLC",
]


def test_sl_suffix_matches_dotted_sl():
    assert normalize_for_match("Acme SL") == normalize_for_match("ACME, S.L.")
    idx = DatechIndex(["ACME, S.L."])
    assert idx.find("Acme SL") == "ACME, S.L."


def test_normalize_strips_suffixes_and_punct():
    assert normalize_for_match("Acme CAD Solutions, Inc.") == "ACME CAD SOLUTIONS"
    assert normalize_for_match("Redshift Reprographics LLC (DBA RedRepro)") == "REDSHIFT REPROGRAPHICS"


def test_exact_and_token_match():
    idx = DatechIndex(DATECH)
    assert idx.find("ACME CAD Solutions Inc") == "ACME CAD SOLUTIONS INC"
    # token subset: "Redshift Reprographics" matches ignoring the LLC suffix
    assert idx.find("Redshift Reprographics") == "Redshift Reprographics LLC"


def test_no_false_positive_on_generic_words():
    idx = DatechIndex(DATECH)
    # shares only the stop-word "SOLUTIONS" — must NOT match
    assert idx.find("Global IT Solutions") is None


def test_single_generic_token_does_not_cross_match():
    # both reduce to the single generic brand token {APPLIED} — must not cross-match
    idx = DatechIndex(["APPLIED COMPUTER", "APPLIED SOFTWARE TECH INC"])
    assert idx.find("Applied Software") is None


def test_multi_token_subset_matches():
    idx = DatechIndex(["CADAC GROUP AEC B.V.", "CADAC GROUP B.V."])
    assert idx.find("Cadac Group") is not None


def test_load_skips_null_reseller(tmp_path):
    p = tmp_path / "inv.csv"
    p.write_text('"Reseller"\n"NULL"\n""\n"Real Co Inc"\n', encoding="utf-8-sig")
    assert load_datech_names(p) == ["Real Co Inc"]


def test_country_aware_match_prefers_same_market():
    recs = [
        {"name": "ACES DIRECT B.V.", "country": "Netherlands", "geo": "EMEA", "region": "Benelux", "csn": "NL1"},
        {"name": "ACES DIRECT B.V.", "country": "Belgium", "geo": "EMEA", "region": "Benelux", "csn": "BE1"},
    ]
    idx = DatechIndex([], records=recs)
    m = idx.match("Aces Direct BV", country="Belgium")
    assert m["name"] == "ACES DIRECT B.V." and m["country"] == "Belgium"
    assert m["same_country"] is True and m["csn"] == "BE1"
    assert idx.match("Aces Direct BV", country="France")["same_country"] is False
    assert idx.match("Totally Unrelated Co", country="Belgium") is None


def test_match_companies_map():
    got = match_companies(["ACME CAD Solutions", "Unrelated Widgets Co"], DATECH)
    assert got == {"ACME CAD Solutions": "ACME CAD SOLUTIONS INC"}


def test_load_datech_names_from_csv(tmp_path):
    p = tmp_path / "invoicing.csv"
    p.write_text('"Reseller"\n"Acme CAD Solutions Inc"\n"Redshift Reprographics LLC"\n',
                 encoding="utf-8-sig")
    names = load_datech_names(p)
    assert "Acme CAD Solutions Inc" in names and len(names) == 2
