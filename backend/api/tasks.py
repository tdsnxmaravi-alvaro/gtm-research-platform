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


def request_cancel(name: str, mode: str = "stop") -> None:
    p = _control_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"cancel": True, "mode": mode}), encoding="utf-8")


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


def cancel_mode(name: str) -> str:
    p = _control_path(name)
    if not p.exists():
        return "stop"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("mode", "stop")
    except (json.JSONDecodeError, OSError):
        return "stop"


# --------------------------------------------------------------------------- #
# Relaunch — clear this campaign's per-run state/outputs so the pipeline runs
# from scratch. The GLOBAL caches (research + contacts) live at the data root
# (out.parent/.gtm_cache), OUTSIDE the campaign folder, so they are preserved:
# Apollo is never re-charged for a domain already enriched anywhere.
# --------------------------------------------------------------------------- #
def reset_campaign_state(name: str) -> None:
    """Delete a campaign's research/enrich/consolidate/outreach artifacts.

    Removes state checkpoints and outputs so a relaunch re-runs everything, while
    keeping the shared domain caches at the data root untouched.
    """
    out = _out_dir(name)
    for fname in ("state.json", "results.csv",
                  "enrich_state.json", "contacts.csv",
                  "master.csv", "master.xlsx",
                  "phone_reveals.json", "enrich_credits.json"):
        f = out / fname
        if f.exists():
            try:
                f.unlink()
            except OSError:
                pass
    eml_dir = out / "eml"
    if eml_dir.exists():
        for f in eml_dir.glob("*.eml"):
            try:
                f.unlink()
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# Single stage
# --------------------------------------------------------------------------- #
@shared_task
def run_stage(run_id: int, cfg_dict: dict, stage: str, name: str,
             fresh: bool = False) -> str:
    """Execute one pipeline stage and record status + a short summary on the Run.

    When ``fresh`` is set (relaunch), research bypasses the research cache so LARA
    is genuinely re-queried and any prompt/vertical/country changes take effect.
    """
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
                                   progress_cb=_progress, should_cancel=_should_cancel,
                                   use_research_cache=config.research_cache and not fresh)
            count = len(results)
            tiers = Counter((r.get("final_tier") or r.get("tier") or "?") for r in results)
            breakdown = ", ".join(f"{k}:{tiers[k]}" for k in ("A", "B", "C", "D") if tiers.get(k))
            summary = f"{count} companies" + (f" — {breakdown}" if breakdown else "")
        elif stage == "enrich":
            from gtm.enrichment import run_enrichment
            from gtm.consolidate import build_master
            contacts = run_enrichment(config, out_dir=out_dir,
                                      should_cancel=_should_cancel, progress_cb=_progress)
            count = len(contacts)
            emails = sum(1 for c in contacts if getattr(c, "email", ""))
            phones = sum(1 for c in contacts if getattr(c, "direct_phone", ""))
            enr = config.enrichment
            if enr.provider.value == "apollo":
                real = None
                try:
                    real = json.loads((out_dir / "enrich_credits.json")
                                      .read_text(encoding="utf-8")).get("apollo_credits")
                except (OSError, ValueError):
                    real = None
                if real is not None:
                    summary = (f"{count} contacts ({emails} emails, {phones} phones) "
                               f"— {real} Apollo credits used")
                else:
                    est = emails * enr.credits_per_email + phones * enr.credits_per_phone
                    summary = (f"{count} contacts ({emails} emails, {phones} phones) "
                               f"— ~{est} Apollo credits (est.)")
            else:
                summary = f"{count} contacts ({emails} emails, {phones} phones) — LARA (no credits)"
            # Refresh the master with the new contacts (join onto the shortlist).
            build_master(config, out_dir=out_dir, min_tier=config.outreach.min_tier)
        elif stage == "consolidate":
            from gtm.consolidate import build_master
            count = len(build_master(config, out_dir=out_dir,
                                     min_tier=config.outreach.min_tier,
                                     progress_cb=_progress))
            summary = f"{count} qualified companies (tier ≥ {config.outreach.min_tier})"
        elif stage == "outreach":
            from gtm.outreach import run_outreach
            from gtm.outreach.email_gen import _lara_agent
            count = len(run_outreach(config, out_dir=out_dir, progress_cb=_progress))
            ai = _lara_agent() is not None
            summary = (f"{count} .eml drafts — "
                       + ("AI-personalized (LARA)" if ai
                          else "template (set LARA_OUTREACH_ASSISTANT_ID for AI)"))
        else:
            raise ValueError(f"unknown stage: {stage}")

        if _should_cancel():
            run.status = "paused" if cancel_mode(name) == "pause" else "canceled"
            verb = "Paused" if run.status == "paused" else "Stopped"
            run.message = f"{verb} — {summary}"
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
def run_pipeline(campaign_id: int, fresh: bool = False) -> None:
    """Run research -> (enrich) -> consolidate -> (outreach) sequentially.

    Skips enrich when nothing is requested and outreach when disabled. Each stage
    is resumable; stopping leaves saved state so a later Start resumes.

    When ``fresh`` is set (relaunch), the campaign's per-run state/outputs are
    cleared first so every stage runs from scratch. Shared domain caches are kept
    so Apollo is never re-charged for an already-enriched company.
    """
    close_old_connections()
    campaign = Campaign.objects.get(pk=campaign_id)
    name, cfg = campaign.name, campaign.config
    if fresh:
        reset_campaign_state(name)
    clear_cancel(name)

    from gtm.config.schema import CampaignConfig
    config = CampaignConfig(**cfg)
    # consolidate BEFORE enrich: build the deduped, tier-filtered shortlist first,
    # then enrich only that shortlist (saves credits), then refresh the master.
    stages = ["research", "consolidate"]
    if config.enrichment.want.value != "none":
        stages.append("enrich")
    if config.outreach.enabled:
        stages.append("outreach")

    for stage in stages:
        if is_canceled(name):
            break
        run = Run.objects.create(campaign=campaign, stage=stage, status="pending")
        run_stage(run.id, cfg, stage, name, fresh=fresh)
        run.refresh_from_db()
        if run.status in ("error", "canceled"):
            break
    close_old_connections()
