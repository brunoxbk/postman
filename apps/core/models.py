from django.conf import settings
from django.db import models
from django.utils import timezone


class SyncLog(models.Model):
    day = models.DateField(unique=True)
    requests = models.PositiveIntegerField(default=0)
    quota_limit = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-day"]

    def __str__(self):
        return f"{self.day} — {self.requests}/{self.quota_limit}"

    @classmethod
    def _row(cls):
        today = timezone.localdate()
        obj, _ = cls.objects.get_or_create(
            day=today,
            defaults={"quota_limit": getattr(settings, "COTA_MENSAL", 900)},
        )
        return obj

    @classmethod
    def increment(cls) -> int:
        obj = cls._row()
        obj.requests += 1
        obj.save()
        return obj.requests

    @classmethod
    def count_today(cls) -> int:
        return cls._row().requests

    @classmethod
    def increment_and_get_count(cls) -> int:
        return cls.increment()

    @classmethod
    def is_paused(cls) -> bool:
        row = cls._row()
        return row.requests >= row.quota_limit