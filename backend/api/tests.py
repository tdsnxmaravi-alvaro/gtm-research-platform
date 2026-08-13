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





