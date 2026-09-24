from django.contrib.auth import views as auth_views
from django.urls import path

from apps.trackings import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("partials/dashboard/", views.dashboard_blocks, name="dashboard_blocks"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("packages/new/", views.package_new, name="package_new"),
    path("packages/<str:tracking_code>/", views.package_detail, name="package_detail"),
    path("packages/<str:tracking_code>/edit/", views.package_edit, name="package_edit"),
    path("packages/<str:tracking_code>/sync/", views.package_sync_now, name="package_sync_now"),
    path("packages/<str:tracking_code>/reabrir/", views.package_reactivate, name="package_reactivate"),
    path("packages/<str:tracking_code>/delete/", views.package_delete, name="package_delete"),
]