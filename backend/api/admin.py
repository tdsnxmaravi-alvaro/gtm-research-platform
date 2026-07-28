from django.contrib import admin

from .models import Campaign, Run


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name",)


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ("campaign", "stage", "status", "result_count", "created_at", "finished_at")
    list_filter = ("stage", "status")
