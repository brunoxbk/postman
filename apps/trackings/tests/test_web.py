from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

from apps.trackings.models import Package


class WebTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("admin", password="pw12345")

    def login(self):
        self.client.login(username="admin", password="pw12345")

    def test_login_required(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)

    def test_dashboard(self):
        self.login()
        Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        resp = self.client.get("/")
        self.assertContains(resp, "AM101610575BR")

    def test_create_package_flow(self):
        self.login()
        resp = self.client.post("/packages/new/", {
            "tracking_code": "AJ123456789012345",
            "label": "Encomenda Anjun",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Package.objects.filter(tracking_code="AJ123456789012345").exists())
        created = Package.objects.get(tracking_code="AJ123456789012345")
        self.assertEqual(created.carrier, "anjun")

    def test_detail_shows_events(self):
        self.login()
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        p.events.create(occurred_at="2025-03-03 23:30:03", status_key="BDE",
                        status_label="Entregue", fingerprint="f1")
        resp = self.client.get(f"/packages/{p.tracking_code}/")
        self.assertContains(resp, "Entregue")

    def test_dashboard_marks_delayed_for_display(self):
        self.login()
        Package.objects.create(
            tracking_code="AM101610575BR",
            carrier="correios",
            estimated_delivery="2020-01-01",
            state="in_transit",
        )
        resp = self.client.get("/")
        self.assertContains(resp, "Atrasada")

    def test_dashboard_shows_quota_and_carrier_filter(self):
        self.login()
        resp = self.client.get("/")
        self.assertContains(resp, "Cota diária")
        self.assertContains(resp, "900")
        self.assertContains(resp, 'name="carrier"')

    def test_dashboard_search_by_label(self):
        self.login()
        p = Package.objects.create(
            tracking_code="AM101610575BR",
            carrier="correios",
            label="Na casa da mãe",
        )
        resp = self.client.get("/", {"q": "mãe"})
        self.assertContains(resp, p.tracking_code)

    def test_dashboard_shows_label_and_sort(self):
        self.login()
        Package.objects.create(tracking_code="AM101610575BR", carrier="correios", label="Meu pacote")
        resp = self.client.get("/")
        self.assertContains(resp, "Meu pacote")
        self.assertContains(resp, "Último evento")
        self.assertContains(resp, 'name="sort"')

    def test_dashboard_paginates(self):
        self.login()
        for i in range(26):
            Package.objects.create(tracking_code=f"AM{i:09d}BR", carrier="correios")
        resp = self.client.get("/")
        self.assertContains(resp, "Página 1 de 2")
        self.assertContains(resp, "Próxima")

    def test_sync_now_get_is_blocked(self):
        self.login()
        Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        resp = self.client.get("/packages/AM101610575BR/sync/")
        self.assertEqual(resp.status_code, 405)

    def test_sync_now_post(self):
        self.login()
        Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        with mock.patch("apps.trackings.views.sync_package", return_value=True):
            resp = self.client.post("/packages/AM101610575BR/sync/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/packages/AM101610575BR/")

    def test_dashboard_auto_refreshes(self):
        self.login()
        resp = self.client.get("/")
        self.assertContains(resp, "data-auto-refresh")
        self.assertContains(resp, 'data-interval="60000"')

    def test_detail_has_lock_copy_count(self):
        self.login()
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        p.events.create(occurred_at="2025-03-03 23:30:03", status_key="BDE",
                        status_label="Entregue", fingerprint="f1")
        resp = self.client.get(f"/packages/{p.tracking_code}/")
        self.assertContains(resp, 'class="js-lock"')
        self.assertContains(resp, 'id="copy-code"')
        self.assertContains(resp, "(1)")

    def test_sync_now_quota_paused_message(self):
        self.login()
        Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        with mock.patch("apps.trackings.views.sync_package", return_value=None):
            resp = self.client.post("/packages/AM101610575BR/sync/", follow=True)
        self.assertContains(resp, "Cota diária atingida")

    def test_create_normalizes_uppercase(self):
        self.login()
        resp = self.client.post("/packages/new/", {
            "tracking_code": "am101610575br",
            "label": "Minúsculo",
        })
        self.assertEqual(resp.status_code, 302)
        p = Package.objects.get(tracking_code="AM101610575BR")
        self.assertEqual(p.carrier, "correios")

    def test_duplicate_case_variant_rejected(self):
        self.login()
        Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        resp = self.client.post("/packages/new/", {
            "tracking_code": "am101610575br",
            "label": "Duplicata",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "já existe")

    def test_terminal_hides_sync_and_offers_reopen(self):
        self.login()
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        p.mark_terminal("100", "delivered")
        p.save()
        resp = self.client.get(f"/packages/{p.tracking_code}/")
        self.assertNotContains(resp, "Atualizar agora")
        self.assertContains(resp, "Reabrir rastreio")

    def test_reactivate_package(self):
        self.login()
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        p.mark_terminal("100", "delivered")
        p.save()
        resp = self.client.post(f"/packages/{p.tracking_code}/reabrir/")
        self.assertEqual(resp.status_code, 302)
        p.refresh_from_db()
        self.assertTrue(p.is_active)
        self.assertEqual(p.state, "in_transit")