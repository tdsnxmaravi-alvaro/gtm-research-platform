"""Celery tasks — run pipeline stages (async with a broker; in a background
thread locally). Progress + a file-based cancel flag make runs resumable and
stoppable without losing work (research/enrich persist state to disk)."""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import close_old_connections

from .models import Campaign, Run


def _out_dir(name: str) -> Path:
    return Path(settings.GTM_DATA_ROOT) / name


# --------------------------------------------------------------------------- #
# Cancellation — a small flag file per campaign, checked between batches/stages.
# --------------------------------------------------------------------------- #
def _control_path(name: str) -> Path:
    return _out_dir(name) / "control.json"


def request_cancel(name: str) -> None:
    p = _control_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"cancel": True}), encoding="utf-8")


def clear_cancel(name: str) -> None:
    p = _control_path(name)
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass


def is_canceled(name: str) -> bool:
    p = _control_path(name)
    if not p.exists():
        return False
    try:
        return bool(json.loads(p.read_text(encoding="utf-8")).get("cancel"))
    except (json.JSONDecodeError, OSError):
        return False


# --------------------------------------------------------------------------- #
# Single stage
# --------------------------------------------------------------------------- #
@shared_task
def run_stage(run_id: int, cfg_dict: dict, stage: str, name: str) -> str:
    """Execute one pipeline stage and record status + a short summary on the Run."""
    close_old_connections()
    run = Run.objects.get(pk=run_id)
    run.status = "running"
    run.save(update_fields=["status"])
    out_dir = _out_dir(name)

    def _progress(done: int, total: int) -> None:
        Run.objects.filter(pk=run_id).update(processed=done, total=total)

    def _should_cancel() -> bool:
        return is_canceled(name)

    try:
        from gtm.config.schema import CampaignConfig
        config = CampaignConfig(**cfg_dict)
        if stage == "research":
            from gtm.research import run_campaign
            results = run_campaign(config, out_dir=out_dir, limit=config.process_limit,
                                   progress_cb=_progress, should_cancel=_should_cancel)
            count = len(results)
            tiers = Counter((r.get("final_tier") or r.get("tier") or "?") for r in results)
            breakdown = ", ".join(f"{k}:{tiers[k]}" for k in ("A", "B", "C", "D") if tiers.get(k))
            summary = f"{count} companies" + (f" — {breakdown}" if breakdown else "")
        elif stage == "enrich":
            from gtm.enrichment import run_enrichment
            contacts = run_enrichment(config, out_dir=out_dir, should_cancel=_should_cancel)
            count = len(contacts)
            summary = f"{count} contacts"
        elif stage == "consolidate":
            from gtm.consolidate import build_master
            count = len(build_master(config, out_dir=out_dir))
            summary = f"{count} master rows"
        elif stage == "outreach":
            from gtm.outreach import run_outreach
            count = len(run_outreach(config, out_dir=out_dir))
            summary = f"{count} .eml drafts"
        else:
            raise ValueError(f"unknown stage: {stage}")

        if _should_cancel():
            run.status = "canceled"
            run.message = f"Stopped — {summary}"
        else:
            run.status = "done"
            run.message = summary
        run.result_count = count
    except Exception as exc:  # noqa: BLE001 - record failure
        run.status = "error"
        run.message = str(exc)[:2000]
    finally:
        run.finished_at = datetime.now(timezone.utc)
        run.save()
        close_old_connections()
    return run.status


# --------------------------------------------------------------------------- #
# Full pipeline — run the stages in order, stopping on error or cancel.
# --------------------------------------------------------------------------- #
def run_pipeline(campaign_id: int) -> None:
    """Run research -> (enrich) -> consolidate -> (outreach) sequentially.

    Skips enrich when nothing is requested and outreach when disabled. Each stage
    is resumable; stopping leaves saved state so a later Start resumes.
    """
    close_old_connections()
    campaign = Campaign.objects.get(pk=campaign_id)
    name, cfg = campaign.name, campaign.config
    clear_cancel(name)

    from gtm.config.schema import CampaignConfig
    config = CampaignConfig(**cfg)
    stages = ["research"]
    if config.enrichment.want.value != "none":
        stages.append("enrich")
    stages.append("consolidate")
    if config.outreach.enabled:
        stages.append("outreach")

    for stage in stages:
        if is_canceled(name):
            break
        run = Run.objects.create(campaign=campaign, stage=stage, status="pending")
        run_stage(run.id, cfg, stage, name)
        run.refresh_from_db()
        if run.status in ("error", "canceled"):
            break
    close_old_connections()
