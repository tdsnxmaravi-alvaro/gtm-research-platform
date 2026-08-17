"""CLI smoke tests (no network)."""

from gtm.cli import main


def test_cli_validate_sample_campaign(capsys):
    main(["validate", "campaigns/spain-bricscad.yaml"])
    out = capsys.readouterr().out
    assert "OK" in out
    assert "resellers" in out


def test_cli_estimate_credits(capsys):
    main(["estimate", "campaigns/spain-bricscad.yaml", "--companies", "10"])
    out = capsys.readouterr().out.lower()
    assert "credits" in out
    assert "companies=10" in out.replace(" ", "")
