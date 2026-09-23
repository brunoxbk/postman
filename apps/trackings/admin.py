from django.contrib import admin

from apps.trackings.models import Package, TrackingEvent


@admin.action(description="Re-sincronizar encomendas selecionadas")
def resync_packages(modeladmin, request, queryset):
    from apps.carriers.sync import sync_package

    ok = erro = 0
    for package in queryset:
        try:
            result = sync_package(package)
        except Exception:  # noqa: BLE001
            result = False
        if result is True:
            ok += 1
        else:
            erro += 1
    modeladmin.message_user(request, f"{ok} encomenda(s) sincronizadas, {erro} com erro.")


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = (
        "tracking_code", "label", "state", "is_active", "is_delayed",
        "last_event_at", "last_synced_at",
    )
    list_filter = ("state", "carrier", "is_active", "is_delayed")
    search_fields = ("tracking_code", "label")
    actions = [resync_packages]


@admin.register(TrackingEvent)
class TrackingEventAdmin(admin.ModelAdmin):
    list_display = ("package", "occurred_at", "status_label", "location")
    list_filter = ("package__carrier",)
    search_fields = ("package__tracking_code", "status_label")
    date_hierarchy = "occurred_at"