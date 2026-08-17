"""Tests for atomic JSON writes, CSV formula safety, and CSV checkpoints."""

from gtm.ingest import write_rows_csv
from gtm.io import CsvCheckpoint, atomic_write_json, csv_safe, csv_unescape, read_csv_dicts


def test_atomic_write_json_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    atomic_write_json(path, {"done": ["Acme"], "n": 1})
    text = path.read_text(encoding="utf-8")
    assert '"Acme"' in text
    assert not list(tmp_path.glob("*.tmp"))


def test_csv_safe_quotes_hyperlink_formula():
    payload = '=HYPERLINK("http://evil.example","x")'
    assert csv_safe(payload).startswith("'")
    assert csv_safe(payload) == "'" + payload
    assert csv_unescape(csv_safe(payload)) == payload
    assert csv_safe("Acme SA") == "Acme SA"
    assert csv_safe(88) == 88
    assert csv_unescape("O'Brien") == "O'Brien"
    assert csv_unescape(csv_safe("+34600111222")) == "+34600111222"


def test_write_rows_csv_neutralizes_formula(tmp_path):
    path = tmp_path / "out.csv"
    write_rows_csv(
        [{"company": "Acme", "notes": '=HYPERLINK("http://evil.example","x")'}],
        path,
        columns=["company", "notes"],
    )
    raw = path.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK" in raw
    rows = read_csv_dicts(path)
    assert rows[0]["notes"].startswith("=")


def test_csv_checkpoint_writes_every_n_and_on_flush(tmp_path):
    path = tmp_path / "rows.csv"
    ck = CsvCheckpoint(path, ["company"], every=3)
    assert ck.note([{"company": "A"}]) is False
    assert not path.exists()
    assert ck.note([{"company": "A"}, {"company": "B"}]) is False
    assert ck.note([{"company": "A"}, {"company": "B"}, {"company": "C"}]) is True
    assert path.exists()
    ck.note([{"company": "A"}, {"company": "B"}, {"company": "C"}, {"company": "D"}])
    ck.flush([{"company": "A"}, {"company": "B"}, {"company": "C"}, {"company": "D"}])
    rows = read_csv_dicts(path)
    assert [r["company"] for r in rows] == ["A", "B", "C", "D"]
