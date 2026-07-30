"""Tests for Phase 3: consolidate (master) + outreach (.eml)."""

import email
import email.policy

from gtm.config import CampaignConfig
from gtm.consolidate import normalize_name, build_master
from gtm.outreach import render_template, write_eml
from gtm.outreach.eml import apply_template


def _cfg(**over):
    d = dict(name="p3", target_type="resellers", mode="provided", country="Spain",
             products=[{"name": "Trimble", "value_prop": "design software",
                        "fit_criteria": ["sells software"]}],
             provided_list_path="x.csv",
             outreach={"enabled": True, "language": "es", "min_tier": "B",
                       "sender_name": "Ana BDR", "sender_email": "ana@tdsynnex.com"})
    d.update(over)
    return CampaignConfig(**d)


def test_normalize_name():
    assert normalize_name("SERVICIOS, S.A.") == "SERVICIOS"
    assert normalize_name("Acme Inc.") == "ACME"
    assert normalize_name("Foo (Bar) LLC") == "FOO"


def test_build_master_joins_results_and_contacts(tmp_path):
    out = tmp_path / "camp"
    out.mkdir()
    (out / "results.csv").write_text(
        "company,website,final_tier,score,fit_summary,recommended_products,evidence_urls,product\n"
        "Acme SA,https://a.es,A,88,strong fit,SketchUp,https://a.es/x,Trimble\n"
        "Beta SL,https://b.es,C,55,weak,SketchUp,https://b.es/y,Trimble\n",
        encoding="utf-8-sig")
    (out / "contacts.csv").write_text(
        "company,contact_name,title,email,email_status,direct_phone,linkedin\n"
        "Acme SA,Ana Ruiz,CEO,ana@a.es,verified,,\n"
        "Acme SA,Bob Diaz,CTO,bob@a.es,verified,,\n",
        encoding="utf-8-sig")

    c = _cfg()
    rows = build_master(c, out_dir=out, min_tier="B")
    # Beta (C) excluded by min_tier B; Acme has 2 contacts
    assert len(rows) == 2
    assert all(r["company"] == "Acme SA" for r in rows)
    assert rows[0]["tier"] == "A"
    assert (out / "master.csv").exists()
    assert (out / "master.xlsx").exists()


def test_render_template_es():
    c = _cfg()
    subj, body = render_template(c, {"company": "Acme SA", "contact_name": "Ana Ruiz",
                                     "recommended_products": "SketchUp", "product": "Trimble",
                                     "fit_summary": "encaja bien"})
    assert "Acme SA" in subj
    assert body.startswith("Hola Ana")
    assert "Trimble" in body
    assert "Ana BDR" in body  # sender in signature


def test_write_eml_is_smtp_and_unsent(tmp_path):
    path = write_eml(tmp_path / "d.eml", to_email="ana@a.es", to_name="Ana",
                     subject="Hola", body="Hola Ana\n\nSaludos",
                     from_email="bdr@tdsynnex.com", from_name="BDR")
    raw = path.read_bytes()
    # SMTP policy -> CRLF line endings (avoids Outlook quoted-printable corruption)
    assert b"\r\n" in raw
    with open(path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=email.policy.default)
    assert msg["X-Unsent"] == "1"
    assert msg["Subject"] == "Hola"
    assert msg.is_multipart()  # text + html alternative


def test_apply_template_replaces_marker():
    html = '<div class="box"><img src="cid:banner"><div>{{BODY}}</div>-- TD SYNNEX</div>'
    out = apply_template(html, "Hola Acme.\n\nSaludos")
    assert "{{BODY}}" not in out
    assert "Hola Acme." in out and "Saludos" in out
    assert 'class="box"' in out and "TD SYNNEX" in out  # box preserved
    assert apply_template("<div>no marker</div>", "x") is None


def test_write_eml_uses_branded_template_and_carries_inline_image(tmp_path):
    # Build a branded sample .eml with a {{BODY}} marker + inline CID image.
    from email.message import EmailMessage
    tpl = EmailMessage()
    tpl["Subject"], tpl["From"], tpl["To"] = "s", "a@b.com", "c@d.com"
    tpl.set_content("plain")
    tpl.add_alternative(
        '<html><body><div style="border:1px solid #ccc">'
        '<img src="cid:banner1"><div>{{BODY}}</div><div>-- TD SYNNEX</div>'
        "</div></body></html>",
        subtype="html",
    )
    tpl.get_payload()[-1].add_related(b"\x89PNG_fake", maintype="image",
                                      subtype="png", cid="<banner1>")
    sample = tmp_path / "sample.eml"
    sample.write_bytes(tpl.as_bytes(policy=email.policy.SMTP))

    out = write_eml(tmp_path / "out.eml", to_email="x@y.com", subject="Hi",
                    body="Hola Acme.\n\nEsto es una prueba.", template_eml=str(sample))
    msg = email.message_from_bytes(out.read_bytes(), policy=email.policy.default)
    html = next(p.get_content() for p in msg.walk() if p.get_content_type() == "text/html")
    imgs = [p for p in msg.walk() if p.get_content_maintype() == "image"]
    assert "{{BODY}}" not in html and "Hola Acme." in html
    assert "border:1px solid #ccc" in html and "cid:banner1" in html  # box + ref kept
    assert len(imgs) == 1 and imgs[0]["Content-ID"] == "<banner1>"  # inline image carried
