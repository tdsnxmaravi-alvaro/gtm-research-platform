import threading
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Campaign, Run
from .serializers import CampaignSerializer, RunSerializer


def _out_dir(name: str) -> Path:
    return Path(settings.GTM_DATA_ROOT) / name


def _load_config(cfg: dict):
    from gtm.config.schema import CampaignConfig
    return CampaignConfig(**cfg)


def _read_csv(path: Path) -> list[dict]:
    import csv
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _execute(run_id: int, cfg_dict: dict, stage: str, out_dir: Path):
    """Run a pipeline stage in a background thread and record status."""
    close_old_connections()
    run = Run.objects.get(pk=run_id)
    run.status = "running"
    run.save(update_fields=["status"])
    try:
        config = _load_config(cfg_dict)
        if stage == "research":
            from gtm.research import run_campaign
            rows = run_campaign(config, out_dir=out_dir)
            count = len(rows)
        elif stage == "enrich":
            from gtm.enrichment import run_enrichment
            rows = run_enrichment(config, out_dir=out_dir)
            count = len(rows)
        elif stage == "consolidate":
            from gtm.consolidate import build_master
            rows = build_master(config, out_dir=out_dir)
            count = len(rows)
        elif stage == "outreach":
            from gtm.outreach import run_outreach
            rows = run_outreach(config, out_dir=out_dir)
            count = len(rows)
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


class CampaignViewSet(viewsets.ModelViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer

    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        """Validate the stored config against the schema."""
        campaign = self.get_object()
        try:
            _load_config(campaign.config)
        except Exception as exc:  # noqa: BLE001
            return Response({"valid": False, "error": str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({"valid": True})

    def _start(self, campaign, stage) -> Run:
        run = Run.objects.create(campaign=campaign, stage=stage, status="pending")
        t = threading.Thread(
            target=_execute,
            args=(run.id, campaign.config, stage, _out_dir(campaign.name)),
            daemon=True,
        )
        t.start()
        return run

    @action(detail=True, methods=["post"])
    def research(self, request, pk=None):
        run = self._start(self.get_object(), "research")
        return Response(RunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def enrich(self, request, pk=None):
        run = self._start(self.get_object(), "enrich")
        return Response(RunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def consolidate(self, request, pk=None):
        run = self._start(self.get_object(), "consolidate")
        return Response(RunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def outreach(self, request, pk=None):
        run = self._start(self.get_object(), "outreach")
        return Response(RunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        campaign = self.get_object()
        rows = _read_csv(_out_dir(campaign.name) / "results.csv")
        return Response({"count": len(rows), "results": rows})

    @action(detail=True, methods=["get"])
    def contacts(self, request, pk=None):
        campaign = self.get_object()
        rows = _read_csv(_out_dir(campaign.name) / "contacts.csv")
        return Response({"count": len(rows), "contacts": rows})


class RunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Run.objects.all()
    serializer_class = RunSerializer
