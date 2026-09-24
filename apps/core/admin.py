from django.contrib import admin

from apps.core.models import SyncLog


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("month", "requests", "quota_limit")