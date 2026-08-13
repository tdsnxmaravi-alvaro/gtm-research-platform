from django.db import migrations


def seed_providers(apps, schema_editor):
    ProviderSetting = apps.get_model("api", "ProviderSetting")
    defaults = [
        dict(name="lara", label="LARA (TD SYNNEX)", type="lara", model="",
             web_search=True, enabled=True, is_default_research=True,
             api_key_env="LARA_RESEARCH_API_KEY", endpoint_env="LARA_API_URL",
             assistant_id_env="LARA_RESEARCH_ASSISTANT_ID"),
        dict(name="azure-sol", label="Azure Foundry — gpt-5.6-sol",
             type="azure_foundry", model="gpt-5.6-sol", web_search=True,
             enabled=False, is_default_research=False,
             api_key_env="AZURE_FOUNDRY_API_KEY",
             endpoint_env="AZURE_FOUNDRY_ENDPOINT"),
    ]
    for d in defaults:
        ProviderSetting.objects.get_or_create(name=d["name"], defaults=d)


def unseed_providers(apps, schema_editor):
    ProviderSetting = apps.get_model("api", "ProviderSetting")
    ProviderSetting.objects.filter(name__in=["lara", "azure-sol"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0006_providersetting"),
    ]

    operations = [
        migrations.RunPython(seed_providers, unseed_providers),
    ]
