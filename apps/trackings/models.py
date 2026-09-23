import hashlib

from django.db import models

from apps.carriers.constants import CARRIER_CHOICES

STATE_IN_TRANSIT = "in_transit"
STATE_DELIVERED = "delivered"
STATE_FAILED = "failed"
STATE_RETURNED = "returned"
STATE_INACTIVE = "inactive"

STATE_CHOICES = [
    (STATE_IN_TRANSIT, "Em trânsito"),
    (STATE_DELIVERED, "Entregue"),
    (STATE_FAILED, "Falha"),
    (STATE_RETURNED, "Devolvida"),
    (STATE_INACTIVE, "Encerrada"),
]

TERMINAL_STATES = {STATE_DELIVERED, STATE_FAILED, STATE_RETURNED, STATE_INACTIVE}


class Package(models.Model):
    tracking_code = models.CharField(max_length=64, unique=True)
    carrier = models.CharField(max_length=20, choices=CARRIER_CHOICES, db_index=True)
    label = models.CharField(max_length=128, blank=True)
    document = models.CharField(
        max_length=16,
        blank=True,
        help_text="CPF somente dígitos (obrigatório p/ J&T)",
    )
    status_code = models.CharField(max_length=64, blank=True)
    status_label = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    last_event_at = models.DateTimeField(null=True, blank=True)
    estimated_delivery = models.DateField(null=True, blank=True)
    state = models.CharField(
        max_length=20,
        choices=STATE_CHOICES,
        default=STATE_IN_TRANSIT,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    is_delayed = models.BooleanField(default=False)
    delivered_notified_at = models.DateTimeField(null=True, blank=True)
    delay_notified_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    last_raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.label or self.tracking_code

    def mark_terminal(self, status_code: str, state: str) -> None:
        self.status_code = status_code
        self.state = state
        self.is_active = False
        self.is_delayed = False

    @property
    def display_code(self) -> str:
        return self.label or self.tracking_code

    @property
    def masked_document(self) -> str:
        if not self.document:
            return ""
        digits = "".join(ch for ch in self.document if ch.isdigit())
        if len(digits) < 6:
            return digits
        return f"***.***.***-{digits[-2:]}"


class TrackingEvent(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="events")
    occurred_at = models.DateTimeField(null=True, blank=True)
    status_key = models.CharField(max_length=128)
    status_label = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    fingerprint = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]

    def __str__(self):
        return f"{self.package.tracking_code} — {self.status_label}"

    @staticmethod
    def make_fingerprint(package_id: int, occurred_at, status_key: str, status_label: str) -> str:
        stamp = occurred_at.isoformat() if occurred_at else ""
        base = f"{package_id};{stamp};{status_key};{status_label}".lower()
        return hashlib.sha1(base.encode("utf-8")).hexdigest()