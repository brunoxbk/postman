from django.contrib import admin

from apps.core.models import SyncLog


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("day", "requests", "quota_limit")