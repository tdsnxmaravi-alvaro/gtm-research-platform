"""Atomic JSON writes, CSV formula safety, checkpoints, and file locks."""

from __future__ import annotations

import csv
import json
import os
from contextlib import contextmanager
from pathlib import Path

# Excel treats these as formula / command prefixes when a CSV/XLSX is opened.
_FORMULA_PREFIXES = frozenset("=+-@")


def csv_safe(value):
    """Neutralize CSV/Excel formula injection.

    Prefix a quote when the value (after leading spaces/tabs) starts with
    ``=``, ``+``, ``-``, or ``@``, or when it starts with a tab/CR. Numbers
    stay numbers so score columns remain numeric in XLSX.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    s = str(value)
    if not s:
        return s
    if s[0] in "\t\r":
        return "'" + s
    stripped = s.lstrip(" \t")
    if stripped[:1] in _FORMULA_PREFIXES:
        return "'" + s
    return s


def csv_unescape(value):
    """Undo ``csv_safe`` so pipeline CSVs round-trip (phones like ``+34…``)."""
    if not isinstance(value, str) or not value.startswith("'"):
        return value
    rest = value[1:]
    if rest[:1] in _FORMULA_PREFIXES or rest[:1] in "\t\r":
        return rest
    stripped = rest.lstrip(" \t")
    if stripped[:1] in _FORMULA_PREFIXES:
        return rest
    return value


def read_csv_dicts(path: str | Path) -> list[dict]:
    """Read a UTF-8-SIG CSV written by this package, undoing ``csv_safe``."""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return [{k: csv_unescape(v) for k, v in row.items()} for row in rows]


def csv_checkpoint_every() -> int:
    """How often to rewrite a growing results/contacts CSV (companies, not bytes)."""
    raw = os.environ.get("GTM_CSV_CHECKPOINT_EVERY", "25")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 25


class CsvCheckpoint:
    """Rewrite ``path`` every ``every`` updates, and whenever ``flush`` is used.

    Resume state that lives next to the CSV must be saved only when this
    actually writes, otherwise a crash can mark work done without the rows.
    """

    def __init__(self, path: str | Path, columns: list[str], every: int | None = None):
        self.path = Path(path)
        self.columns = columns
        self.every = max(1, every if every is not None else csv_checkpoint_every())
        self._since = 0

    def note(self, rows: list[dict], *, force: bool = False) -> bool:
        """Count one update. Write if ``force`` or the interval elapsed. True if written."""
        self._since += 1
        if force or self._since >= self.every:
            self.flush(rows)
            return True
        return False

    def flush(self, rows: list[dict]) -> None:
        from .ingest.parser import write_rows_csv
        write_rows_csv(rows, self.path, columns=self.columns)
        self._since = 0


def atomic_write_json(path: str | Path, obj, *, indent: int = 2) -> None:
    """Write JSON via a temp file + replace so a crash cannot leave a truncated file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, indent=indent, ensure_ascii=False)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


@contextmanager
def file_lock(path: str | Path):
    """Exclusive lock on ``path.lock`` so two processes cannot clobber the same JSON."""
    path = Path(path)
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            if fh.read(1) == b"":
                fh.write(b"\0")
                fh.flush()
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()
