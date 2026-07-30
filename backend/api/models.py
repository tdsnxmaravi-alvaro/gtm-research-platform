from django.db import models


class Campaign(models.Model):
    """A campaign = the full CampaignConfig stored as JSON + metadata."""

    name = models.SlugField(max_length=120, unique=True)
    config = models.JSONField(help_text="CampaignConfig as JSON")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Run(models.Model):
    """One execution of a pipeline stage for a campaign."""

    STAGE = [(s, s) for s in ("research", "enrich", "consolidate", "outreach")]
    STATUS = [(s, s) for s in ("pending", "running", "done", "error")]

    campaign = models.ForeignKey(Campaign, related_name="runs", on_delete=models.CASCADE)
    stage = models.CharField(max_length=20, choices=STAGE)
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    message = models.TextField(blank=True, default="")
    result_count = models.IntegerField(default=0)
    processed = models.IntegerField(default=0)   # items processed so far (progress)
    total = models.IntegerField(default=0)        # total items to process (progress)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.campaign.name}:{self.stage}:{self.status}"
