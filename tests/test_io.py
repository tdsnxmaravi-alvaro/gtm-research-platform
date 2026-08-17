"""Tests for atomic JSON writes."""

from gtm.io import atomic_write_json


def test_atomic_write_json_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    atomic_write_json(path, {"done": ["Acme"], "n": 1})
    text = path.read_text(encoding="utf-8")
    assert '"Acme"' in text
    assert not list(tmp_path.glob("*.tmp"))
