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

