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


def test_cli_prompt_renders_without_network(capsys):
    main(["prompt", "campaigns/spain-bricscad.yaml", "--company", "Acme CAD"])
    out = capsys.readouterr().out
    assert "Acme CAD" in out
    assert len(out) > 80


def test_cli_inspect_csv(tmp_path, capsys):
    p = tmp_path / "list.csv"
    p.write_text("company,website\nAcme,https://acme.com\n", encoding="utf-8")
    main(["inspect", str(p), "--no-ai"])
    out = capsys.readouterr().out
    assert "Acme" in out or "company" in out.lower()
    assert "Ready to run" in out


def test_cli_run_delegates_to_research(monkeypatch):
    called = {}

    def fake_run(cfg, **kw):
        called["limit"] = kw.get("limit")
        called["delay"] = kw.get("delay")
        return []

    monkeypatch.setattr("gtm.cli.run_campaign", fake_run)
    main(["run", "campaigns/spain-bricscad.yaml", "--limit", "3", "--delay", "0"])
    assert called["limit"] == 3
    assert called["delay"] == 0


def test_cli_consolidate_and_outreach_delegate(monkeypatch):
    seen = []
    monkeypatch.setattr("gtm.cli.build_master", lambda cfg, **kw: seen.append("consolidate") or [])
    monkeypatch.setattr("gtm.cli.run_outreach", lambda cfg, **kw: seen.append("outreach") or [])
    main(["consolidate", "campaigns/spain-bricscad.yaml"])
    main(["outreach", "campaigns/spain-bricscad.yaml"])
    assert seen == ["consolidate", "outreach"]
