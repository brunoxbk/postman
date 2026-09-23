from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.trackings.api import HealthView, PackageViewSet
from apps.trackings.api_schema import SchemaView

router = DefaultRouter()
router.register("packages", PackageViewSet, basename="packages")

urlpatterns = [
    path("v1/", include(router.urls)),
    path("v1/health/", HealthView.as_view(), name="health"),
    path("v1/schema/", SchemaView.as_view(), name="api_schema"),
]