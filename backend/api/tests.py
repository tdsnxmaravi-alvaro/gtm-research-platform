from rest_framework.test import APITestCase

from api.models import Campaign

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
