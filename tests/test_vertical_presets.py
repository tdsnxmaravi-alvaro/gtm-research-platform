"""Tests for discover-mode vendor vertical presets (issue #14)."""

from gtm.prompts.vendor_presets import VENDOR_PRESETS
from gtm.prompts.vertical_presets import (
    VERTICAL_PRESETS, VENDOR_VERTICALS, VENDOR_EXCLUSIONS, VENDOR_OWN_PRODUCTS,
    verticals_for, vertical_preset, exclusions_for, exclusion_note,
    CORE, SECONDARY, DEFER, TIERS, _validate,
)

EXPECTED_COUNTS = {
    "Trimble": 13, "Bricsys": 17, "DraftSight": 14,
    "Newforma": 13, "Novade": 18, "Unity": 14,
}


def test_import_validates():
    _validate()  # raises on any inconsistency


def test_every_vendor_preset_has_verticals():
    for vendor in VENDOR_PRESETS:
        assert VENDOR_VERTICALS.get(vendor), f"{vendor} has no verticals"


def test_all_slugs_and_tiers_valid():
    for vendor, items in VENDOR_VERTICALS.items():
        slugs = [s for s, _ in items]
        assert len(slugs) == len(set(slugs)), f"{vendor} has duplicate verticals"
        for slug, tier in items:
            assert slug in VERTICAL_PRESETS
            assert tier in TIERS


def test_counts_match_refined_lists():
    for vendor, n in EXPECTED_COUNTS.items():
        assert len(VENDOR_VERTICALS[vendor]) == n, f"{vendor} count changed"


def test_catalogue_entries_are_complete():
    for slug, v in VERTICAL_PRESETS.items():
        assert v["name"] and v["focus"]
        assert isinstance(v["example_reseller_software"], list)
        assert v["example_reseller_software"], f"{slug} has no example software"


def test_no_orphan_verticals():
    used = {s for items in VENDOR_VERTICALS.values() for s, _ in items}
    orphans = set(VERTICAL_PRESETS) - used
    assert not orphans, f"unused verticals: {sorted(orphans)}"


def test_verticals_for_default_includes_all_tiers():
    v = verticals_for("Trimble")  # default returns all so the UI can render Defer unchecked
    tiers = {x["tier"] for x in v}
    assert tiers == {CORE, SECONDARY, DEFER}


def test_verticals_for_checked_tiers_excludes_defer():
    v = verticals_for("Trimble", tiers=(CORE, SECONDARY))
    assert v and DEFER not in {x["tier"] for x in v}


def test_verticals_for_defer_only():
    v = verticals_for("Bricsys", tiers=(DEFER,))
    assert v and all(x["tier"] == DEFER for x in v)
    assert {x["slug"] for x in v} == {"additive-manufacturing", "cae-simulation", "mes-digital-twin"}


def test_verticals_for_shape():
    for x in verticals_for("Unity"):
        assert {"slug", "name", "focus", "example_reseller_software", "tier"} <= set(x)


def test_verticals_for_unknown_vendor_is_empty():
    assert verticals_for("Nope") == []


def test_vertical_preset_lookup():
    assert vertical_preset("solidworks-vars")["name"].startswith("SOLIDWORKS")


def test_draftsight_does_not_exclude_dassault():
    joined = " ".join(exclusions_for("DraftSight")).lower()
    assert "dassault" not in joined and "solidworks" not in joined
    assert "Autodesk" in exclusions_for("DraftSight")


def test_unity_excludes_unreal():
    assert any("unreal" in k.lower() for k in exclusions_for("Unity"))


def test_exclusion_note_is_english_and_nonempty():
    note = exclusion_note("Trimble")
    assert note.startswith("Excludes") and "Autodesk Gold/Platinum/Premier" in note
    assert exclusion_note("Nope") == ""


def test_every_vendor_has_exclusions():
    for vendor in VENDOR_PRESETS:
        assert vendor in VENDOR_EXCLUSIONS


# Products each vendor OWNS — must never appear in its own verticals' landscape
# (discover recruits NEW independent resellers, not ones already selling our product).
def test_no_vendor_self_reference_in_own_verticals():
    for vendor, tokens in VENDOR_OWN_PRODUCTS.items():
        for v in verticals_for(vendor, tiers=TIERS):
            hay = " ".join(v["example_reseller_software"]).lower()
            for tok in tokens:
                assert tok.lower() not in hay, (
                    f"{vendor}/{v['slug']} landscape lists own product '{tok}'")
