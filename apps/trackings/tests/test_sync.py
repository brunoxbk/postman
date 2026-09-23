import json
from pathlib import Path
from unittest import mock

from django.test import TestCase

from apps.carriers.sync import sync_package
from apps.trackings.models import Package

FIXTURES = Path(__file__).parent.parent.parent / "carriers" / "tests" / "fixtures"


class FakeClient:
    def __init__(self, raw):
        self.raw = raw
        self.calls = 0

    def fetch(self, path, params):
        self.calls += 1
        return self.raw


class SyncTestCase(TestCase):
    def test_sync_package_delivered(self):
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        raw = json.loads(FIXTURES.joinpath("correios.json").read_text())
        ok = sync_package(p, FakeClient(raw))
        self.assertTrue(ok)
        p2 = Package.objects.get(pk=p.pk)
        self.assertFalse(p2.is_active)
        self.assertEqual(p2.state, "delivered")
        self.assertEqual(p2.events.count(), 2)

    def test_sync_package_uses_quota(self):
        p = Package.objects.create(tracking_code="X1", carrier="correios")
        with mock.patch("apps.carriers.sync.SyncLog.is_paused", return_value=True):
            res = sync_package(p, FakeClient({}))
        self.assertIsNone(res)
        self.assertIn("Cota", Package.objects.get(pk=p.pk).last_error)

    def test_sync_jt_without_document(self):
        p = Package.objects.create(tracking_code="888030556767025", carrier="jtexpress")
        res = sync_package(p, FakeClient({}))
        self.assertFalse(res)
        self.assertIn("CPF", Package.objects.get(pk=p.pk).last_error)