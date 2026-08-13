from rest_framework.routers import DefaultRouter

from .views import CampaignViewSet, RunViewSet, ProviderSettingViewSet

router = DefaultRouter()
router.register("campaigns", CampaignViewSet)
router.register("runs", RunViewSet)
router.register("providers", ProviderSettingViewSet)

urlpatterns = router.urls
