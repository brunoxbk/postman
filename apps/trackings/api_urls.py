from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.trackings.api import HealthView, PackageViewSet

router = DefaultRouter()
router.register("packages", PackageViewSet, basename="packages")

urlpatterns = [
    path("v1/", include(router.urls)),
    path("v1/health/", HealthView.as_view(), name="health"),
]