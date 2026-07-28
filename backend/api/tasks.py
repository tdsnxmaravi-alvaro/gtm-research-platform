"""Celery tasks — run pipeline stages asynchronously."""

from datetime import datetime, timezone
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import close_old_connections

from .models import Run


def _out_dir(name: str) -> Path:
    return Path(settings.GTM_DATA_ROOT) / name


@shared_task
def run_stage(run_id: int, cfg_dict: dict, stage: str, name: str) -> str:
    """Execute one pipeline stage and record status on the Run."""
    close_old_connections()
    run = Run.objects.get(pk=run_id)
    run.status = "running"
    run.save(update_fields=["status"])
    out_dir = _out_dir(name)
    try:
        from gtm.config.schema import CampaignConfig
        config = CampaignConfig(**cfg_dict)
        if stage == "research":
            from gtm.research import run_campaign
            count = len(run_campaign(config, out_dir=out_dir))
        elif stage == "enrich":
            from gtm.enrichment import run_enrichment
            count = len(run_enrichment(config, out_dir=out_dir))
        elif stage == "consolidate":
            from gtm.consolidate import build_master
            count = len(build_master(config, out_dir=out_dir))
        elif stage == "outreach":
            from gtm.outreach import run_outreach
            count = len(run_outreach(config, out_dir=out_dir))
        else:
            raise ValueError(f"unknown stage: {stage}")
        run.status = "done"
        run.result_count = count
    except Exception as exc:  # noqa: BLE001 - record failure
        run.status = "error"
        run.message = str(exc)[:2000]
    finally:
        run.finished_at = datetime.now(timezone.utc)
        run.save()
        close_old_connections()
    return run.status
