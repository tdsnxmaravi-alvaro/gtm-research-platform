import csv
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Campaign, Run
from .serializers import CampaignSerializer, RunSerializer
from .tasks import run_stage, run_pipeline, request_cancel, clear_cancel

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB cap for provided lists
ALLOWED_LIST_EXT = (".csv", ".xlsx", ".xlsm")
ALLOWED_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp")


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
        from gtm.prompts import build_prompt, enrich_config_dict
        cfg = request.data.get("config", request.data)
        cfg = enrich_config_dict(cfg)
        try:
            config = _load_config(cfg)
        except Exception as exc:  # noqa: BLE001
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        product = config.products[0].model_copy(update={"search_prompt": None})
        vert = config.verticals[0] if config.verticals else None
        prompt = build_prompt(config, product, vertical=vert)
        return Response({"prompt": prompt})

    @action(detail=False, methods=["get"])
    def vendor_preset(self, request):
        """Return the ready-made value prop + fit criteria for a vendor + target_type.

        Feeds the wizard's prompt step so the editable fields start from the
        vendor's qualification framework (country stays a variable).
        """
        from gtm.prompts import preset_for, VENDOR_PRESETS
        vendor = request.query_params.get("vendor", "")
        target_type = request.query_params.get("target_type", "resellers")
        preset = preset_for(vendor, target_type)
        if not preset:
            return Response({"vendor": vendor, "known": False,
                             "vendors": sorted(VENDOR_PRESETS)})
        return Response({
            "vendor": vendor, "known": True,
            "product_name": preset["product_name"],
            "value_prop": preset["value_prop"],
            "fit_criteria": preset["fit_criteria"],
        })

    @action(detail=False, methods=["post"])
    def upload_logo(self, request):
        """Store a logo image for the outreach frame; returns its server path."""
        import uuid

        upload = request.FILES.get("file")
        if not upload:
            return Response({"error": "No file uploaded (field 'file')."},
                            status=status.HTTP_400_BAD_REQUEST)
        ext = Path(upload.name).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXT:
            return Response({"error": "Only PNG/JPG/GIF/WEBP images are supported."},
                            status=status.HTTP_400_BAD_REQUEST)
        if upload.size and upload.size > MAX_UPLOAD_BYTES:
            return Response({"error": "Image exceeds the 10 MB limit."},
                            status=status.HTTP_400_BAD_REQUEST)
        updir = Path(settings.GTM_DATA_ROOT) / "_uploads"
        updir.mkdir(parents=True, exist_ok=True)
        dest = updir / f"logo_{uuid.uuid4().hex[:8]}{ext}"
        with open(dest, "wb") as fh:
            for chunk in upload.chunks():
                fh.write(chunk)
        return Response({"path": str(dest), "name": upload.name})

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
        clear_cancel(campaign.name)
        # With a real broker, dispatch to a worker. In local eager mode, run in a
        # background thread so the request returns immediately and progress (%) is
        # pollable while the stage executes.
        if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            import threading
            threading.Thread(
                target=run_stage,
                args=(run.id, campaign.config, stage, campaign.name),
                daemon=True,
            ).start()
        else:
            run_stage.delay(run.id, campaign.config, stage, campaign.name)
        return run

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Run the whole pipeline (research -> enrich -> consolidate -> outreach)
        phase by phase, stopping on error or when stopped. Resumable."""
        campaign = self.get_object()
        import threading
        threading.Thread(target=run_pipeline, args=(campaign.id,), daemon=True).start()
        return Response({"started": True}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        """Cancel the run. State is saved on disk, so nothing already spent is lost;
        a later Start resumes (never re-charges cached companies)."""
        campaign = self.get_object()
        request_cancel(campaign.name, mode="stop")
        return Response({"stopping": True})

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        """Pause after the current batch/stage — meant to be resumed later (e.g. if
        running low on Apollo credits). Start resumes from where it left off."""
        campaign = self.get_object()
        request_cancel(campaign.name, mode="pause")
        return Response({"pausing": True})

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        """Latest run for this campaign (drives the pipeline progress UI)."""
        campaign = self.get_object()
        run = campaign.runs.first()  # ordered by -created_at
        return Response(RunSerializer(run).data if run else {})

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Download a campaign artifact (Excel/CSV)."""
        campaign = self.get_object()
        which = request.query_params.get("artifact", "master.xlsx")
        allowed = {"master.xlsx", "master.csv", "results.csv", "contacts.csv"}
        if which not in allowed:
            return Response({"error": "unknown artifact"}, status=status.HTTP_400_BAD_REQUEST)
        path = _out_dir(campaign.name) / which
        if not path.exists():
            return Response({"error": f"{which} not found — run the pipeline first."},
                            status=status.HTTP_404_NOT_FOUND)
        return FileResponse(open(path, "rb"), as_attachment=True,
                            filename=f"{campaign.name}_{which}")

    @action(detail=True, methods=["get"], url_path="download_eml")
    def download_eml(self, request, pk=None):
        """Download all generated .eml drafts as a single zip."""
        import io
        import zipfile

        campaign = self.get_object()
        eml_dir = _out_dir(campaign.name) / "eml"
        files = sorted(eml_dir.glob("*.eml")) if eml_dir.exists() else []
        if not files:
            return Response({"error": "No .eml drafts — run outreach first."},
                            status=status.HTTP_404_NOT_FOUND)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in files:
                z.write(p, p.name)
        resp = HttpResponse(buf.getvalue(), content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="{campaign.name}_eml.zip"'
        return resp

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
