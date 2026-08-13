from django.db import models


class Campaign(models.Model):
    """A campaign = the full CampaignConfig stored as JSON + metadata."""

    name = models.SlugField(max_length=120, unique=True)
    config = models.JSONField(help_text="CampaignConfig as JSON")
    deleted = models.BooleanField(default=False)  # soft-delete: hide but keep data
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Run(models.Model):
    """One execution of a pipeline stage for a campaign."""

    STAGE = [(s, s) for s in ("research", "enrich", "consolidate", "outreach")]
    STATUS = [(s, s) for s in ("pending", "running", "done", "error", "canceled", "paused")]

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


class ProviderSetting(models.Model):
    """A selectable research LLM provider (global catalog).

    Secrets are NEVER stored here — only the ENV VAR NAMES that hold them. The
    catalog is what the wizard offers per campaign and what Settings toggles on/off.
    """

    TYPE = [(t, t) for t in ("lara", "azure_openai", "azure_foundry", "manual")]

    name = models.SlugField(max_length=60, unique=True)  # config provider `name`
    label = models.CharField(max_length=120, blank=True, default="")
    type = models.CharField(max_length=20, choices=TYPE)
    model = models.CharField(max_length=120, blank=True, default="")  # deployment
    web_search = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)          # available for use
    is_default_research = models.BooleanField(default=False)
    api_key_env = models.CharField(max_length=80, blank=True, default="")
    endpoint_env = models.CharField(max_length=80, blank=True, default="")
    assistant_id_env = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default_research", "name"]

    def __str__(self):
        return self.name
