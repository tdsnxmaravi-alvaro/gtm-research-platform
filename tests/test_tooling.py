"""Tooling contracts (#31): ruff in CI, pinned lockfile, ruff as a dev extra."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_ruff_is_a_dev_dependency():
    assert "ruff" in PYPROJECT


def test_ci_runs_ruff_check():
    assert "ruff check" in CI


def test_lockfile_exists():
    assert (ROOT / "uv.lock").is_file() or (ROOT / "requirements.lock").is_file()


def test_ci_installs_from_the_lockfile():
    frozen = "--frozen" in CI or "uv.lock" in CI or "requirements.lock" in CI
    assert frozen
