from rest_framework.routers import DefaultRouter

from .views import CampaignViewSet, RunViewSet

router = DefaultRouter()
router.register("campaigns", CampaignViewSet)
router.register("runs", RunViewSet)

urlpatterns = router.urls
