from datetime import date

from django.db import IntegrityError
from django.test import TestCase

from apps.carriers.constants import CARRIER_CORREIOS
from apps.trackings.models import (
    STATE_DELIVERED,
    STATE_IN_TRANSIT,
    Package,
    TrackingEvent,
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

    def test_terminal_resets_is_delayed(self):
        p = Package.objects.create(
            tracking_code="AM101610575BR",
            carrier=CARRIER_CORREIOS,
            state=STATE_IN_TRANSIT,
            is_delayed=True,
        )
        p.mark_terminal("ENTREGUE", "delivered")
        self.assertFalse(p.is_delayed)

    def test_masked_document(self):
        p = Package(tracking_code="X1", carrier=CARRIER_CORREIOS, document="12345678901")
        self.assertEqual(p.masked_document, "***.***.***-01")

    def test_is_overdue_in_transit_past_eta(self):
        p = Package(
            tracking_code="X1", carrier=CARRIER_CORREIOS,
            state=STATE_IN_TRANSIT, estimated_delivery=date(2020, 1, 1),
        )
        self.assertTrue(p.is_overdue)

    def test_is_overdue_false_when_future_eta(self):
        p = Package(
            tracking_code="X1", carrier=CARRIER_CORREIOS,
            state=STATE_IN_TRANSIT, estimated_delivery=date(2099, 1, 1),
        )
        self.assertFalse(p.is_overdue)

    def test_is_overdue_false_when_no_eta(self):
        p = Package(tracking_code="X1", carrier=CARRIER_CORREIOS, state=STATE_IN_TRANSIT)
        self.assertFalse(p.is_overdue)

    def test_is_overdue_false_when_delivered(self):
        p = Package(
            tracking_code="X1", carrier=CARRIER_CORREIOS,
            state=STATE_DELIVERED, estimated_delivery=date(2020, 1, 1),
        )
        self.assertFalse(p.is_overdue)


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