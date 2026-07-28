from rest_framework import serializers

from .models import Campaign, Run


class RunSerializer(serializers.ModelSerializer):
    class Meta:
        model = Run
        fields = ["id", "campaign", "stage", "status", "message",
                  "result_count", "created_at", "finished_at"]
        read_only_fields = fields


class CampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = ["id", "name", "config", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_config(self, value):
        """Validate the config against the CampaignConfig schema."""
        from gtm.config.schema import CampaignConfig
        from pydantic import ValidationError
        try:
            CampaignConfig(**value)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.errors())
        return value
