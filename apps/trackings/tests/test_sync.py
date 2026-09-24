import json
from pathlib import Path
from unittest import mock, skipUnless

from django.core import mail
from django.db import connection
from django.test import TestCase, override_settings

from apps.carriers.exceptions import PacoteVicioClientError
from apps.carriers.payload import NormalizedPayload
from apps.carriers.sync import SyncResult, _apply_events, sync_all, sync_package
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
        self.assertIs(ok, SyncResult.OK)
        p2 = Package.objects.get(pk=p.pk)
        self.assertFalse(p2.is_active)
        self.assertEqual(p2.state, "delivered")
        self.assertEqual(p2.events.count(), 2)

    def test_sync_package_uses_quota(self):
        p = Package.objects.create(tracking_code="X1", carrier="correios")
        with mock.patch("apps.carriers.sync.SyncLog.is_paused", return_value=True):
            res = sync_package(p, FakeClient({}))
        self.assertIs(res, SyncResult.PAUSED)
        self.assertIn("Cota", Package.objects.get(pk=p.pk).last_error)

    def test_sync_jt_without_document(self):
        p = Package.objects.create(tracking_code="888030556767025", carrier="jtexpress")
        res = sync_package(p, FakeClient({}))
        self.assertIs(res, SyncResult.NO_DOCUMENT)
        self.assertIn("CPF", Package.objects.get(pk=p.pk).last_error)

    def test_sync_honors_terminal_state(self):
        p = Package.objects.create(tracking_code="X1", carrier="correios")
        normalized = NormalizedPayload(
            tracking_code="X1", status_code="FLH", status_label="FALHA",
            location="", last_event_at=None, estimated_delivery=None,
            is_terminal=True, terminal_state="failed", events=[], raw={},
        )
        _apply_events(p, normalized)
        p.refresh_from_db()
        self.assertEqual(p.state, "failed")
        self.assertFalse(p.is_active)

    def test_sync_terminal_defaults_to_delivered(self):
        p = Package.objects.create(tracking_code="X1", carrier="correios")
        normalized = NormalizedPayload(
            tracking_code="X1", status_code="E", status_label="ENTREGUE",
            location="", last_event_at=None, estimated_delivery=None,
            is_terminal=True, terminal_state=None, events=[], raw={},
        )
        _apply_events(p, normalized)
        p.refresh_from_db()
        self.assertEqual(p.state, "delivered")

    def test_resync_does_not_duplicate_events(self):
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        raw = json.loads(FIXTURES.joinpath("correios.json").read_text())
        self.assertIs(sync_package(p, FakeClient(raw)), SyncResult.OK)
        self.assertIs(sync_package(p, FakeClient(raw)), SyncResult.OK)
        self.assertEqual(Package.objects.get(pk=p.pk).events.count(), 2)

    def test_terminal_clears_last_raw(self):
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        raw = json.loads(FIXTURES.joinpath("correios.json").read_text())
        self.assertIs(sync_package(p, FakeClient(raw)), SyncResult.OK)
        self.assertEqual(Package.objects.get(pk=p.pk).last_raw, {})

    def test_client_error_404_deactivates_package(self):
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")

        class BadClient:
            def fetch(self, path, params):
                raise PacoteVicioClientError(404, "não encontrado")

        res = sync_package(p, BadClient())
        self.assertIs(res, SyncResult.ERROR)
        p.refresh_from_db()
        self.assertFalse(p.is_active)
        self.assertIn("404", p.last_error)

    def test_client_error_401_keeps_package_active(self):
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")

        class BadClient:
            def fetch(self, path, params):
                raise PacoteVicioClientError(401, "chave inválida")

        res = sync_package(p, BadClient())
        self.assertIs(res, SyncResult.ERROR)
        p.refresh_from_db()
        self.assertTrue(p.is_active)
        self.assertIn("401", p.last_error)


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


@override_settings(SYNC_WORKERS=1)
class SyncAllTestCase(TestCase):
    def test_unexpected_error_does_not_stop_batch(self):
        good = Package.objects.create(tracking_code="X1", carrier="correios")
        bad = Package.objects.create(tracking_code="X2", carrier="correios")

        def fake_sync(pkg, client):
            if pkg.pk == bad.pk:
                raise ValueError("boom")
            return SyncResult.OK

        with mock.patch("apps.carriers.sync.sync_package", side_effect=fake_sync):
            results = sync_all(FakeClient({}))

        self.assertEqual(results["ok"], 1)
        self.assertEqual(results["erro"], 1)
        bad.refresh_from_db()
        self.assertIn("boom", bad.last_error)
        good.refresh_from_db()
        self.assertEqual(good.last_error, "")

    def test_paused_result_counted(self):
        Package.objects.create(tracking_code="X1", carrier="correios")
        with mock.patch("apps.carriers.sync.sync_package", return_value=SyncResult.PAUSED):
            results = sync_all(FakeClient({}))
        self.assertEqual(results["pausado"], 1)
        self.assertEqual(results["ok"], 0)


@override_settings(SYNC_WORKERS=4)
@skipUnless(connection.vendor == "postgresql", "Paralelismo exige Postgres (sqlite em memória trava em threads)")
class SyncAllParallelTestCase(TestCase):
    def test_parallel_packages_are_classified(self):
        for i in range(3):
            Package.objects.create(tracking_code=f"AM{i:09d}BR", carrier="correios")
        with mock.patch("apps.carriers.sync.sync_package", return_value=SyncResult.OK):
            results = sync_all(FakeClient({}))
        self.assertEqual(results["ok"], 3)
        self.assertEqual(results["erro"], 0)