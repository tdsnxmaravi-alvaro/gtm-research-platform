from rest_framework import serializers

from .models import Campaign, Run, ProviderSetting


class RunSerializer(serializers.ModelSerializer):
    class Meta:
        model = Run
        fields = ["id", "campaign", "stage", "status", "message",
                  "result_count", "processed", "total", "created_at", "finished_at"]
        read_only_fields = fields


class CampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = ["id", "name", "config", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_config(self, value):
        """Validate the config against the CampaignConfig schema.

        Also fills vendor-preset defaults (value prop / fit criteria / scoring rubric)
        for the selected vendor so the stored config carries the qualification
        framework into research and outreach.
        """
        from gtm.config.schema import CampaignConfig
        from gtm.prompts import enrich_config_dict
        from pydantic import ValidationError
        value = enrich_config_dict(value)
        try:
            CampaignConfig(**value)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.errors())
        return value


_DEFAULT_KEY_ENV = {
    "lara": "LARA_RESEARCH_API_KEY",
    "azure_openai": "AZURE_OPENAI_API_KEY",
    "azure_foundry": "AZURE_FOUNDRY_API_KEY",
}
_DEFAULT_ENDPOINT_ENV = {
    "azure_openai": "AZURE_OPENAI_ENDPOINT",
    "azure_foundry": "AZURE_FOUNDRY_ENDPOINT",
}


class ProviderSettingSerializer(serializers.ModelSerializer):
    """Catalog entry. `configured` reports (without exposing secrets) whether the
    referenced env vars are set, so the UI can warn when a key is missing."""

    configured = serializers.SerializerMethodField()

    class Meta:
        model = ProviderSetting
        fields = ["id", "name", "label", "type", "model", "web_search", "enabled",
                  "is_default_research", "api_key_env", "endpoint_env",
                  "endpoint_url", "assistant_id_env", "configured"]
        read_only_fields = ["id", "configured"]

    def get_configured(self, obj) -> bool:
        import os
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        if obj.type == "manual":
            return True
        key_env = obj.api_key_env or _DEFAULT_KEY_ENV.get(obj.type, "")
        if key_env and not os.getenv(key_env):
            return False
        if obj.type in ("azure_openai", "azure_foundry") and not obj.endpoint_url:
            ep = obj.endpoint_env or _DEFAULT_ENDPOINT_ENV.get(obj.type, "")
            if ep and not os.getenv(ep):
                return False
        return True
