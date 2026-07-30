"""Regression tests for the research cross-campaign cache and vendor .oft templates."""

import csv
import json
import re
from pathlib import Path

import pytest

from gtm.config.schema import CampaignConfig
from gtm.research.runner import run_campaign


def _cfg(path, **over):
    d = dict(name="c4", target_type="resellers", mode="provided", country="Spain",
             vendor="Trimble", products=[{"name": "Trimble", "fit_criteria": ["x"]}],
             provided_list_path=str(path))
    d.update(over)
    return CampaignConfig(**d)


class _Resp:
    def __init__(self, text):
        self.text = text


class _Stub:
    """Fake provider that echoes every company named in the prompt."""

    def __init__(self):
        self.calls = 0

    def send(self, prompt):
        self.calls += 1
        comps = re.findall(r"\d+\.\s*([^|\n]+?)\s*\|", prompt)
        results = [
            {"company": c.strip(), "website": c.strip().lower().replace(" ", "") + ".com",
             "dimension_scores": [{"name": "x", "points": 5, "max": 10,
                                   "evidence_url": "http://a"}]}
            for c in comps
        ]
        return _Resp(json.dumps({"results": results}))


def test_research_cache_reused_across_campaigns(tmp_path):
    lst = tmp_path / "list.csv"
    lst.write_text("company,website\nAlpha,alpha.com\nBeta,beta.com\n", encoding="utf-8")
    cfg = _cfg(lst)
    s1 = _Stub()
    run_campaign(cfg, provider=s1, out_dir=tmp_path / "campA", delay=0)
    s2 = _Stub()
    run_campaign(cfg, provider=s2, out_dir=tmp_path / "campB", delay=0)
    assert s1.calls >= 1
    assert s2.calls == 0  # all reused from the shared research cache
    rows = list(csv.DictReader(open(tmp_path / "campB" / "results.csv", encoding="utf-8-sig")))
    assert {r["company"] for r in rows} == {"Alpha", "Beta"}


def test_research_cache_disabled(tmp_path):
    lst = tmp_path / "list.csv"
    lst.write_text("company,website\nAlpha,alpha.com\n", encoding="utf-8")
    cfg = _cfg(lst, name="c4b", research_cache=False)
    s1 = _Stub()
    run_campaign(cfg, provider=s1, out_dir=tmp_path / "a", delay=0)
    s2 = _Stub()
    run_campaign(cfg, provider=s2, out_dir=tmp_path / "b", delay=0)
    assert s2.calls >= 1  # cache disabled -> fresh research


def test_vendor_oft_template_to_eml(tmp_path):
    import email
    import email.policy

    from gtm.outreach.oft import find_vendor_template, vendor_template_eml

    if not find_vendor_template("Bricsys"):
        pytest.skip("Bricsys .oft template not present in templates/")
    eml = vendor_template_eml("Bricsys", tmp_path)
    assert eml and Path(eml).exists()
    msg = email.message_from_bytes(Path(eml).read_bytes(), policy=email.policy.default)
    html = next(p.get_content() for p in msg.walk() if p.get_content_type() == "text/html")
    imgs = [p for p in msg.walk() if p.get_content_maintype() == "image"]
    assert "{{BODY}}" in html          # injectable body marker
    assert len(imgs) >= 1              # logo carried as inline image
