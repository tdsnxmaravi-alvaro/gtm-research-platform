"""Research stage: orchestrate provider calls, parse + score results."""

from .runner import run_campaign, ingest_manual, OUT_COLS

__all__ = ["run_campaign", "ingest_manual", "OUT_COLS"]
