from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.trackings.admin import TrackingEventAdmin
from apps.trackings.models import Package


class AdminActionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("sessao", password="pw12345")
        cls.package = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")

    def setUp(self):
        self.client.force_login(self.admin)

    def test_resync_packages_action(self):
        with mock.patch("apps.carriers.sync.sync_package", return_value=True):
            resp = self.client.post(
                reverse("admin:trackings_package_changelist"),
                {"action": "resync_packages", "_selected_action": [self.package.pk]},
                follow=True,
            )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "encomenda(s) sincronizadas")

    def test_event_admin_has_date_hierarchy(self):
        resp = self.client.get(reverse("admin:trackings_trackingevent_changelist"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Por carrier")
        self.assertEqual(TrackingEventAdmin.date_hierarchy, "occurred_at")