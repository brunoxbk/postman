from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.trackings.api_urls")),
    path("", include("apps.trackings.web_urls")),
]