import csv
from pathlib import Path

from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Campaign, Run
from .serializers import CampaignSerializer, RunSerializer
from .tasks import run_stage


def _out_dir(name: str) -> Path:
    return Path(settings.GTM_DATA_ROOT) / name


def _load_config(cfg: dict):
    from gtm.config.schema import CampaignConfig
    return CampaignConfig(**cfg)


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


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
        run_stage.delay(run.id, campaign.config, stage, campaign.name)
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
