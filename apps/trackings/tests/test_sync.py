import json
from pathlib import Path
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings

from apps.carriers.sync import sync_all, sync_package
from apps.trackings.models import Package

FIXTURES = Path(__file__).parent.parent.parent / "carriers" / "tests" / "fixtures"


class FakeClient:
    def __init__(self, raw):
        self.raw = raw
        self.calls = 0

    def fetch(self, path, params):
        self.calls += 1
        return self.raw


EMAIL_SETTINGS = {
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "PACOTE_NOTIFY_EMAIL": "destino@example.com",
    "DEFAULT_FROM_EMAIL": "origem@example.com",
}


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


@override_settings(**EMAIL_SETTINGS)
class SyncEmailNotificationTestCase(TestCase):
    def test_email_on_delivery_once(self):
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        raw = json.loads(FIXTURES.joinpath("correios.json").read_text())
        self.assertTrue(sync_package(p, FakeClient(raw)))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Entregue", mail.outbox[0].subject)
        sync_package(p, FakeClient(raw))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNotNone(Package.objects.get(pk=p.pk).delivered_notified_at)

    def test_email_on_delay_once(self):
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        raw = json.loads(FIXTURES.joinpath("correios.json").read_text())
        raw["situacao"] = "C"
        raw["dtPrevista"] = "01/01/2020"
        for ev in raw["eventos"]:
            ev["finalizador"] = "N"
        self.assertTrue(sync_package(p, FakeClient(raw)))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("atraso", mail.outbox[0].subject)
        sync_package(p, FakeClient(raw))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNotNone(Package.objects.get(pk=p.pk).delay_notified_at)

    def test_no_email_without_setting(self):
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        raw = json.loads(FIXTURES.joinpath("correios.json").read_text())
        with override_settings(PACOTE_NOTIFY_EMAIL=""):
            self.assertTrue(sync_package(p, FakeClient(raw)))
        self.assertEqual(len(mail.outbox), 0)

    def test_email_contains_link(self):
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        raw = json.loads(FIXTURES.joinpath("correios.json").read_text())
        with override_settings(PUBLIC_BASE_URL="https://postman.example.com"):
            self.assertTrue(sync_package(p, FakeClient(raw)))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("https://postman.example.com/packages/AM101610575BR/", mail.outbox[0].body)


class SyncAllTestCase(TestCase):
    def test_unexpected_error_does_not_stop_batch(self):
        good = Package.objects.create(tracking_code="X1", carrier="correios")
        bad = Package.objects.create(tracking_code="X2", carrier="correios")

        def fake_sync(pkg, client):
            if pkg.pk == bad.pk:
                raise ValueError("boom")
            return True

        with mock.patch("apps.carriers.sync.sync_package", side_effect=fake_sync):
            results = sync_all(FakeClient({}))

        self.assertEqual(results["ok"], 1)
        self.assertEqual(results["erro"], 1)
        bad.refresh_from_db()
        self.assertIn("boom", bad.last_error)
        good.refresh_from_db()
        self.assertEqual(good.last_error, "")