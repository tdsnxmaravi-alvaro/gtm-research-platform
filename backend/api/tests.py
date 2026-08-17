from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from api.models import Campaign, Run
VALID_CONFIG = {
    "name": "t-api",
    "target_type": "resellers",
    "mode": "provided",
    "country": "Spain",
    "products": [{"name": "Trimble", "value_prop": "design sw",
                  "fit_criteria": ["sells software"]}],
    "provided_list_path": "x.csv",
}


class CampaignApiTests(APITestCase):
    def test_create_list_and_validate(self):
        # Create
        resp = self.client.post("/api/campaigns/",
                                {"name": "t-api", "config": VALID_CONFIG},
                                format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        cid = resp.json()["id"]

        # List
        resp = self.client.get("/api/campaigns/")
        self.assertEqual(resp.json()["count"], 1)

        # Validate action
        resp = self.client.post(f"/api/campaigns/{cid}/validate/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["valid"])

        # Results (nothing run yet)
        resp = self.client.get(f"/api/campaigns/{cid}/results/")
        self.assertEqual(resp.json()["count"], 0)

    def test_stop_marks_running_run_canceled(self):
        campaign = Campaign.objects.create(name="t-stop", config=VALID_CONFIG)
        run = Run.objects.create(campaign=campaign, stage="research", status="running")
        resp = self.client.post(f"/api/campaigns/{campaign.id}/stop/")
        self.assertEqual(resp.status_code, 200, resp.content)
        run.refresh_from_db()
        self.assertEqual(run.status, "canceled")

    def test_pause_marks_running_run_paused(self):
        campaign = Campaign.objects.create(name="t-pause", config=VALID_CONFIG)
        run = Run.objects.create(campaign=campaign, stage="enrich", status="running")
        resp = self.client.post(f"/api/campaigns/{campaign.id}/pause/")
        self.assertEqual(resp.status_code, 200, resp.content)
        run.refresh_from_db()
        self.assertEqual(run.status, "paused")

    def test_invalid_config_rejected(self):
        bad = dict(VALID_CONFIG)
        bad["mode"] = "provided"
        bad.pop("provided_list_path")  # provided requires a list -> invalid
        resp = self.client.post("/api/campaigns/",
                                {"name": "bad", "config": bad}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_vendor_verticals_grouped_by_tier(self):
        resp = self.client.get("/api/campaigns/vendor_verticals/?vendor=Trimble")
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data["known"])
        self.assertEqual(data["default_checked"], ["core", "secondary"])
        self.assertTrue(data["tiers"]["core"])
        # Each item is Vertical-constructible (name/slug/focus/example_software).
        item = data["tiers"]["core"][0]
        for key in ("slug", "name", "focus", "example_software", "tier"):
            self.assertIn(key, item)
        self.assertIn("Autodesk", data["exclusion_note"])

    def test_vendor_verticals_unknown_vendor(self):
        resp = self.client.get("/api/campaigns/vendor_verticals/?vendor=Nope")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["known"])

    def test_datech_countries(self):
        resp = self.client.get("/api/campaigns/datech_countries/")
        self.assertEqual(resp.status_code, 200, resp.content)
        regions = resp.json()["regions"]
        self.assertIn("EMEA", regions)
        self.assertIn("United States", regions["North America"])

    def test_preview_prompt_is_per_vertical(self):
        from gtm.prompts import discover_verticals
        verts = discover_verticals("Trimble", slugs=["structural-steel-detailing",
                                                     "geospatial-survey"])
        cfg = {
            "name": "disc", "target_type": "resellers", "mode": "discover",
            "vendor": "Trimble", "countries": ["United States"],
            "products": [{"name": "Trimble", "value_prop": "vp"}],
            "verticals": verts,
        }
        resp = self.client.post("/api/campaigns/preview_prompt/",
                                {"config": cfg, "vertical": "geospatial-survey"},
                                format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["vertical"], "geospatial-survey")
        geo = next(v for v in verts if v["slug"] == "geospatial-survey")
        self.assertIn(geo["name"], data["prompt"])


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class ResearchTaskTests(APITestCase):
    def test_research_runs_task_eager(self):
        campaign = Campaign.objects.create(name="t-run", config=VALID_CONFIG)
        # Mock the engine so no external LLM call happens; run eagerly in-process.
        with patch("gtm.research.run_campaign", return_value=[{"company": "Acme"}]):
            resp = self.client.post(f"/api/campaigns/{campaign.id}/research/")
        self.assertEqual(resp.status_code, 202)
        run = Run.objects.get(campaign=campaign, stage="research")
        self.assertEqual(run.status, "done")
        self.assertEqual(run.result_count, 1)


class PipelineDispatchTests(APITestCase):
    """#26: Celery .delay() in production; thread/eager locally; one in-flight run."""

    def test_run_pipeline_is_a_celery_task(self):
        from api.tasks import run_pipeline
        self.assertTrue(hasattr(run_pipeline, "delay"),
                        "run_pipeline must be a Celery shared_task")

    def test_start_dispatches_via_delay_when_not_testing(self):
        from api.tasks import run_pipeline
        campaign = Campaign.objects.create(name="t-delay", config=VALID_CONFIG)
        with override_settings(TESTING=False, RUN_STAGES_IN_THREAD=False):
            with patch.object(run_pipeline, "delay") as delay:
                resp = self.client.post(f"/api/campaigns/{campaign.id}/start/")
        self.assertEqual(resp.status_code, 202, resp.content)
        delay.assert_called_once_with(campaign.id)

    def test_start_uses_thread_when_configured(self):
        campaign = Campaign.objects.create(name="t-thread", config=VALID_CONFIG)
        with override_settings(TESTING=False, RUN_STAGES_IN_THREAD=True):
            with patch("threading.Thread") as thread_cls:
                thread_cls.return_value.start = lambda: None
                resp = self.client.post(f"/api/campaigns/{campaign.id}/start/")
        self.assertEqual(resp.status_code, 202, resp.content)
        thread_cls.assert_called_once()
        target = thread_cls.call_args.kwargs.get("target")
        if target is None and thread_cls.call_args.args:
            target = thread_cls.call_args.args[0]
        from api.tasks import run_pipeline
        self.assertIs(target, run_pipeline)
        self.assertTrue(thread_cls.call_args.kwargs.get("daemon"))

    def test_start_rejects_in_flight_run(self):
        campaign = Campaign.objects.create(name="t-busy", config=VALID_CONFIG)
        Run.objects.create(campaign=campaign, stage="research", status="running")
        resp = self.client.post(f"/api/campaigns/{campaign.id}/start/")
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertIn("progress", resp.json().get("error", "").lower()
                      + resp.json().get("detail", "").lower())

    def test_relaunch_rejects_in_flight_run(self):
        campaign = Campaign.objects.create(name="t-busy-rl", config=VALID_CONFIG)
        Run.objects.create(campaign=campaign, stage="enrich", status="pending")
        resp = self.client.post(f"/api/campaigns/{campaign.id}/relaunch/")
        self.assertEqual(resp.status_code, 409, resp.content)

    def test_run_pipeline_stage_order_when_enrich_and_outreach(self):
        from api.tasks import run_pipeline
        cfg = dict(VALID_CONFIG)
        cfg["name"] = "t-order"
        cfg["enrichment"] = {"provider": "lara", "want": "emails"}
        cfg["outreach"] = {"enabled": True, "min_tier": "C", "language": "en"}
        campaign = Campaign.objects.create(name="t-order", config=cfg)
        seen: list[str] = []

        def _fake_stage(run_id, cfg_dict, stage, name, fresh=False):
            seen.append(stage)
            Run.objects.filter(pk=run_id).update(status="done")

        with patch("api.tasks.run_stage", side_effect=_fake_stage):
            run_pipeline(campaign.id)
        self.assertEqual(seen, ["research", "consolidate", "enrich", "outreach"])

    def test_run_pipeline_skips_enrich_and_outreach_when_disabled(self):
        from api.tasks import run_pipeline
        cfg = dict(VALID_CONFIG)
        cfg["name"] = "t-skip"
        cfg["enrichment"] = {"want": "none"}
        cfg["outreach"] = {"enabled": False}
        campaign = Campaign.objects.create(name="t-skip", config=cfg)
        seen: list[str] = []

        def _fake_stage(run_id, cfg_dict, stage, name, fresh=False):
            seen.append(stage)
            Run.objects.filter(pk=run_id).update(status="done")

        with patch("api.tasks.run_stage", side_effect=_fake_stage):
            run_pipeline(campaign.id)
        self.assertEqual(seen, ["research", "consolidate"])


APOLLO_CONFIG = {
    "name": "t-relaunch",
    "target_type": "resellers",
    "mode": "provided",
    "country": "Spain",
    "products": [{"name": "Trimble", "value_prop": "design sw",
                  "fit_criteria": ["sells software"]}],
    "provided_list_path": "x.csv",
    "enrichment": {"provider": "apollo", "want": "emails"},
    "outreach": {"enabled": False, "min_tier": "C"},
}


class RelaunchTests(APITestCase):
    def _tmp_root(self):
        import tempfile
        from pathlib import Path
        return Path(tempfile.mkdtemp())

    def test_reset_clears_outputs_keeps_shared_cache(self):
        from api.tasks import reset_campaign_state
        root = self._tmp_root()
        with override_settings(GTM_DATA_ROOT=root):
            out = root / "t-reset"
            (out / "eml").mkdir(parents=True)
            for f in ("state.json", "results.csv", "enrich_state.json",
                      "contacts.csv", "master.csv", "master.xlsx"):
                (out / f).write_text("x", encoding="utf-8")
            (out / "eml" / "1.eml").write_text("x", encoding="utf-8")
            # Global cache lives at the data root, OUTSIDE the campaign folder.
            cache = root / ".gtm_cache" / "contacts.json"
            cache.parent.mkdir(parents=True)
            cache.write_text("{}", encoding="utf-8")

            reset_campaign_state("t-reset")

            for f in ("state.json", "results.csv", "master.csv"):
                self.assertFalse((out / f).exists(), f)
            self.assertFalse((out / "eml" / "1.eml").exists())
            self.assertTrue(cache.exists(), "shared cache must be preserved")

    def test_relaunch_endpoint_runs_fresh(self):
        campaign = Campaign.objects.create(name="t-relaunch", config=APOLLO_CONFIG)
        with patch("api.views.run_pipeline") as rp:
            resp = self.client.post(f"/api/campaigns/{campaign.id}/relaunch/")
        self.assertEqual(resp.status_code, 202, resp.content)
        rp.assert_called_once_with(campaign.id, fresh=True)

    def test_relaunch_summary_apollo_new_vs_reused(self):
        from gtm.enrichment.cache import ContactCache
        from gtm.enrichment.models import EnrichedContact
        root = self._tmp_root()
        campaign = Campaign.objects.create(name="t-relaunch", config=APOLLO_CONFIG)
        with override_settings(GTM_DATA_ROOT=root):
            out = root / "t-relaunch"
            out.mkdir(parents=True)
            (out / "master.csv").write_text(
                "company,website,final_tier\n"
                "Acme,acme.com,A\n"          # cached -> reused
                "NewCo,newco.com,B\n"        # not cached -> new (would charge)
                "LowCo,low.com,D\n",         # below min_tier C -> ignored
                encoding="utf-8")
            cache = ContactCache(path=root / ".gtm_cache" / "contacts.json")
            cache.put("acme.com", [EnrichedContact(company="Acme", email="a@acme.com")])

            resp = self.client.get(f"/api/campaigns/{campaign.id}/relaunch_summary/")
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data["uses_apollo"])
        self.assertTrue(data["research_from_scratch"])
        self.assertEqual(data["apollo_new_companies"], 1)
        self.assertEqual(data["apollo_reused_companies"], 1)


class ProviderCatalogTests(APITestCase):
    def test_seeded_providers_listed(self):
        resp = self.client.get("/api/providers/")
        self.assertEqual(resp.status_code, 200, resp.content)
        names = {p["name"] for p in (resp.json().get("results") or resp.json())}
        self.assertIn("lara", names)
        self.assertIn("azure-sol", names)

    def test_toggle_enabled_and_exclusive_default(self):
        from api.models import ProviderSetting
        azure = ProviderSetting.objects.get(name="azure-sol")
        # Enable + make default -> lara must lose the default flag.
        resp = self.client.patch(f"/api/providers/{azure.id}/",
                                 {"enabled": True, "is_default_research": True},
                                 format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        azure.refresh_from_db()
        self.assertTrue(azure.enabled)
        self.assertTrue(azure.is_default_research)
        self.assertFalse(ProviderSetting.objects.get(name="lara").is_default_research)

    def test_crud_add_edit_remove_provider(self):
        # Create a new provider entirely via the API (no code change).
        resp = self.client.post("/api/providers/", {
            "name": "gpt-next", "label": "GPT next", "type": "azure_foundry",
            "model": "gpt-next", "endpoint_url": "https://x.services.ai.azure.com/openai/v1",
            "api_key_env": "GPT_NEXT_KEY", "web_search": True,
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        pid = resp.json()["id"]
        # Secret is never stored/echoed — only the env var NAME.
        self.assertNotIn("api_key", resp.json())
        self.assertEqual(resp.json()["api_key_env"], "GPT_NEXT_KEY")
        # Edit
        resp = self.client.patch(f"/api/providers/{pid}/", {"model": "gpt-next-2"},
                                 format="json")
        self.assertEqual(resp.json()["model"], "gpt-next-2")
        # Remove
        resp = self.client.delete(f"/api/providers/{pid}/")
        self.assertEqual(resp.status_code, 204)
        from api.models import ProviderSetting
        self.assertFalse(ProviderSetting.objects.filter(name="gpt-next").exists())


class PhoneDeliveryTests(APITestCase):
    def test_falls_back_to_polling_without_cloudflared(self):
        from unittest.mock import patch
        import api.phone_delivery as pd
        pd._SERVICES.clear()
        with patch.object(pd, "cloudflared_available", return_value=False):
            status = pd.ensure_phone_delivery("t-nocf", "/tmp/ph.json")
        self.assertEqual(status["mode"], "polling")
        self.assertIsNone(status["url"])

    def test_ensure_is_idempotent(self):
        from unittest.mock import patch
        import api.phone_delivery as pd
        pd._SERVICES.clear()
        with patch.object(pd, "cloudflared_available", return_value=False):
            a = pd.ensure_phone_delivery("t-idem", "/tmp/ph.json")
            b = pd.ensure_phone_delivery("t-idem", "/tmp/ph.json")
        self.assertEqual(a, b)
        self.assertEqual(len(pd._SERVICES), 1)


class ApolloCreditsEndpointTests(APITestCase):
    def test_reports_not_configured_without_key(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APOLLO_API_KEY", None)
            with patch("dotenv.load_dotenv", lambda *a, **k: None):
                resp = self.client.get("/api/campaigns/apollo_credits/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(resp.json()["configured"])


class OrchestrationCoverageTests(APITestCase):
    """#30: upload size/ext, download allowlist, start creates a Run, pipeline order."""

    def _tmp_root(self):
        import tempfile
        from pathlib import Path
        return Path(tempfile.mkdtemp())

    def test_upload_list_rejects_missing_file(self):
        resp = self.client.post("/api/campaigns/upload_list/")
        self.assertEqual(resp.status_code, 400)

    def test_upload_list_rejects_disallowed_extension(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("payload.exe", b"MZ", content_type="application/octet-stream")
        resp = self.client.post("/api/campaigns/upload_list/", {"file": f})
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("csv", resp.json().get("error", "").lower())

    def test_upload_list_rejects_oversize(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile(
            "big.csv",
            b"company,website\nAcme,https://acme.com\n",
            content_type="text/csv",
        )
        with patch("api.views.MAX_UPLOAD_BYTES", 10):
            resp = self.client.post("/api/campaigns/upload_list/", {"file": f})
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("limit", resp.json().get("error", "").lower())

    def test_upload_list_accepts_csv(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from pathlib import Path
        root = self._tmp_root()
        f = SimpleUploadedFile(
            "resellers.csv",
            b"company,website,country\nAcme,https://acme.com,Spain\n",
            content_type="text/csv",
        )
        with override_settings(GTM_DATA_ROOT=root):
            with patch("gtm.ingest.schema_ai.ai_available", return_value=False):
                resp = self.client.post("/api/campaigns/upload_list/", {"file": f})
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data.get("path"))
        self.assertTrue(Path(data["path"]).is_file())
        self.assertGreaterEqual(data.get("with_company", 0), 1)

    def test_download_rejects_unknown_artifact(self):
        campaign = Campaign.objects.create(name="t-dl", config=VALID_CONFIG)
        resp = self.client.get(
            f"/api/campaigns/{campaign.id}/download/?artifact=../../../etc/passwd")
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_download_404_when_missing(self):
        campaign = Campaign.objects.create(name="t-dl-miss", config=VALID_CONFIG)
        resp = self.client.get(
            f"/api/campaigns/{campaign.id}/download/?artifact=master.csv")
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_download_serves_allowlisted_artifact(self):
        root = self._tmp_root()
        campaign = Campaign.objects.create(name="t-dl-ok", config=VALID_CONFIG)
        out = root / campaign.name
        out.mkdir(parents=True)
        (out / "master.csv").write_text("company\nAcme\n", encoding="utf-8")
        with override_settings(GTM_DATA_ROOT=root):
            resp = self.client.get(
                f"/api/campaigns/{campaign.id}/download/?artifact=master.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Acme", b"".join(resp.streaming_content))
        resp.close()

    def test_start_creates_a_run(self):
        campaign = Campaign.objects.create(name="t-start-run", config=VALID_CONFIG)

        def _fake_stage(run_id, cfg_dict, stage, name, fresh=False):
            Run.objects.filter(pk=run_id).update(status="done")

        with patch("api.tasks.run_stage", side_effect=_fake_stage):
            resp = self.client.post(f"/api/campaigns/{campaign.id}/start/")
        self.assertEqual(resp.status_code, 202, resp.content)
        self.assertTrue(Run.objects.filter(campaign=campaign).exists())
        stages = list(
            Run.objects.filter(campaign=campaign).order_by("id").values_list("stage", flat=True)
        )
        self.assertEqual(stages[0], "research")
        self.assertIn("consolidate", stages)

    def test_enrich_and_outreach_actions_create_runs(self):
        campaign = Campaign.objects.create(name="t-actions", config=VALID_CONFIG)
        with patch("gtm.enrichment.run_enrichment", return_value=[]):
            with patch("gtm.consolidate.build_master", return_value=[]):
                resp = self.client.post(f"/api/campaigns/{campaign.id}/enrich/")
        self.assertEqual(resp.status_code, 202, resp.content)
        self.assertTrue(Run.objects.filter(campaign=campaign, stage="enrich").exists())

        with patch("gtm.outreach.run_outreach", return_value=[]):
            with patch("gtm.outreach.email_gen._lara_agent", return_value=None):
                resp = self.client.post(f"/api/campaigns/{campaign.id}/outreach/")
        self.assertEqual(resp.status_code, 202, resp.content)
        self.assertTrue(Run.objects.filter(campaign=campaign, stage="outreach").exists())

    def test_run_pipeline_invokes_engine_in_stage_order(self):
        from api.tasks import run_pipeline
        cfg = dict(VALID_CONFIG)
        cfg["name"] = "t-engine-order"
        cfg["enrichment"] = {"provider": "lara", "want": "emails"}
        cfg["outreach"] = {"enabled": True, "min_tier": "C", "language": "en"}
        campaign = Campaign.objects.create(name="t-engine-order", config=cfg)
        seen: list[str] = []

        def track(label, ret):
            def _fn(*_a, **_k):
                seen.append(label)
                return ret
            return _fn

        with (
            patch("gtm.research.run_campaign",
                  side_effect=track("research", [{"company": "Acme"}])),
            patch("gtm.consolidate.build_master",
                  side_effect=track("consolidate", [{"company": "Acme"}])),
            patch("gtm.enrichment.run_enrichment",
                  side_effect=track("enrich", [])),
            patch("gtm.outreach.run_outreach",
                  side_effect=track("outreach", [])),
            patch("gtm.outreach.email_gen._lara_agent", return_value=None),
        ):
            run_pipeline(campaign.id)

        first = []
        for label in seen:
            if label not in first:
                first.append(label)
        self.assertEqual(first, ["research", "consolidate", "enrich", "outreach"])
        self.assertTrue(Run.objects.filter(campaign=campaign, stage="research",
                                           status="done").exists())






