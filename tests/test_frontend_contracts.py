"""Frontend contracts — source-level until a JS test runner exists (#27, #28)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIZARD = (ROOT / "frontend" / "src" / "Wizard.jsx").read_text(encoding="utf-8")
API = (ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
CAMPAIGNS = (ROOT / "frontend" / "src" / "Campaigns.jsx").read_text(encoding="utf-8")


def _outreach_chunk() -> str:
    idx = WIZARD.index('STEPS[step] === "Outreach"')
    return WIZARD[idx : idx + 5000]


def test_outreach_step_has_sender_name_and_email_inputs():
    chunk = _outreach_chunk()
    assert 'set("sender_name")' in chunk
    assert 'set("sender_email")' in chunk


def test_email_preview_iframe_is_sandboxed():
    assert 'sandbox=""' in WIZARD or "sandbox={''}" in WIZARD or 'sandbox={""}' in WIZARD


def test_remap_list_uses_abort_controller():
    assert "AbortController" in WIZARD
    assert "signal" in API


def test_campaigns_stores_one_poll_interval_per_campaign_in_a_ref():
    assert "useRef" in CAMPAIGNS
    assert "pollTimers" in CAMPAIGNS
    assert "setInterval" in CAMPAIGNS


def test_campaigns_clears_poll_intervals_on_unmount():
    assert "return () =>" in CAMPAIGNS
    assert "clearInterval" in CAMPAIGNS
    assert "pollTimers.current" in CAMPAIGNS


def test_campaigns_replaces_existing_interval_instead_of_stacking():
    # Repeat Start/Relaunch must clear the previous timer for that campaign.
    assert "clearPoll" in CAMPAIGNS or "clearInterval(pollTimers" in CAMPAIGNS
