from django.db import IntegrityError
from django.test import TestCase

from apps.carriers.constants import CARRIER_CORREIOS
from apps.trackings.models import (
    Package,
    TrackingEvent,
    STATE_IN_TRANSIT,
)


class PackageModelTestCase(TestCase):
    def test_create_and_terminal(self):
        p = Package.objects.create(
            tracking_code="AM101610575BR",
            carrier=CARRIER_CORREIOS,
            state=STATE_IN_TRANSIT,
        )
        p.mark_terminal("ENTREGUE", "delivered")
        p.save()
        p.refresh_from_db()
        self.assertFalse(p.is_active)
        self.assertEqual(p.state, "delivered")
        self.assertEqual(p.status_code, "ENTREGUE")

    def test_masked_document(self):
        p = Package(tracking_code="X1", carrier=CARRIER_CORREIOS, document="12345678901")
        self.assertEqual(p.masked_document, "***.***.***-01")


class TrackingEventFingerprintTestCase(TestCase):
    def test_dedupe_by_fingerprint(self):
        p = Package.objects.create(tracking_code="X1", carrier=CARRIER_CORREIOS)
        TrackingEvent.objects.create(
            package=p,
            status_key="BDE",
            status_label="Entregue",
            fingerprint="fp-1",
        )
        with self.assertRaises(IntegrityError):
            TrackingEvent.objects.create(
                package=p,
                status_key="BDE",
                status_label="Entregue",
                fingerprint="fp-1",
            )

    def test_fingerprint_deterministic(self):
        self.assertEqual(
            TrackingEvent.make_fingerprint(1, None, "A", "B"),
            TrackingEvent.make_fingerprint(1, None, "A", "B"),
        )