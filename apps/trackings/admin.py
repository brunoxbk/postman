from django.contrib import admin

from apps.trackings.models import Package, TrackingEvent


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ("tracking_code", "state", "is_active", "is_delayed", "last_event_at")
    list_filter = ("state", "carrier", "is_active")
    search_fields = ("tracking_code", "label")


@admin.register(TrackingEvent)
class TrackingEventAdmin(admin.ModelAdmin):
    list_display = ("package", "occurred_at", "status_label")
    search_fields = ("package__tracking_code", "status_label")