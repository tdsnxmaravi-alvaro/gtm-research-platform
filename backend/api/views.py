import csv
from pathlib import Path

from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Campaign, Run
from .serializers import CampaignSerializer, RunSerializer
from .tasks import run_stage

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB cap for provided lists
ALLOWED_LIST_EXT = (".csv", ".xlsx", ".xlsm")


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

    @action(detail=False, methods=["post"])
    def preview_prompt(self, request):
        """Render the research prompt for an unsaved config (wizard prompt builder).

        Always builds from the template (ignores any existing search_prompt) so the
        client can regenerate a fresh prompt. Provided-mode companies are represented
        by the [[COMPANIES]] sentinel, spliced in at run time.
        """
        from gtm.prompts import build_prompt
        cfg = request.data.get("config", request.data)
        try:
            config = _load_config(cfg)
        except Exception as exc:  # noqa: BLE001
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        product = config.products[0].model_copy(update={"search_prompt": None})
        vert = config.verticals[0] if config.verticals else None
        prompt = build_prompt(config, product, vertical=vert)
        return Response({"prompt": prompt})

    @action(detail=False, methods=["post"])
    def upload_list(self, request):
        """Accept a provided list (.csv/.xlsx), store it, and return a column-mapping
        preview (AI schema-mapper when configured, else the deterministic mapping).

        The response feeds the wizard's mapping step: detected company/website/country
        columns, per-row country presence, data-quality warnings and a small sample.
        """
        import uuid

        upload = request.FILES.get("file")
        if not upload:
            return Response({"error": "No file uploaded (field 'file')."},
                            status=status.HTTP_400_BAD_REQUEST)
        ext = Path(upload.name).suffix.lower()
        if ext not in ALLOWED_LIST_EXT:
            return Response({"error": "Only .csv or .xlsx files are supported."},
                            status=status.HTTP_400_BAD_REQUEST)
        if upload.size and upload.size > MAX_UPLOAD_BYTES:
            return Response({"error": "File exceeds the 10 MB limit."},
                            status=status.HTTP_400_BAD_REQUEST)

        updir = Path(settings.GTM_DATA_ROOT) / "_uploads"
        updir.mkdir(parents=True, exist_ok=True)
        stem = "".join(c for c in Path(upload.name).stem if c.isalnum() or c in ("-", "_"))
        dest = updir / f"{uuid.uuid4().hex[:8]}_{(stem or 'list')[:50]}{ext}"
        with open(dest, "wb") as fh:
            for chunk in upload.chunks():
                fh.write(chunk)

        from gtm.ingest.parser import inspect_provided_list, load_provided_list
        from gtm.ingest.schema_ai import ai_available

        try:
            report = inspect_provided_list(dest, use_ai=ai_available())
            report["path"] = str(dest)
            rows = load_provided_list(dest)
            report["sample"] = rows[:5]
            report["has_country_col"] = any(
                v == "country" for v in report.get("mapping", {}).values()
            )
        except Exception as exc:  # noqa: BLE001
            return Response({"error": f"Could not read the list: {exc}"},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(report)

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
