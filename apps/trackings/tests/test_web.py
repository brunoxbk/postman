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