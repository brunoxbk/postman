from unittest import mock

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_api_key.models import APIKey

from apps.carriers.adapters import detect_carrier
from apps.trackings.models import Package


class ApiTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.key = APIKey.objects.create_key(name="teste")[1]

    def auth(self):
        return {"HTTP_AUTHORIZATION": f"Api-Key {self.key}"}

    def test_health(self):
        resp = self.client.get("/api/v1/health/", **self.auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")

    def test_health_is_public(self):
        resp = self.client.get("/api/v1/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")

    def test_schema_is_public(self):
        resp = self.client.get("/api/v1/schema/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["openapi"].split(".")[0], "3")

    def test_create_package(self):
        resp = self.client.post(
            "/api/v1/packages/",
            {"tracking_code": "AM101610575BR", "carrier": "correios", "label": "Meu pacote"},
            format="json", **self.auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertTrue(Package.objects.filter(tracking_code="AM101610575BR").exists())

    def test_create_requires_auth(self):
        resp = self.client.post("/api/v1/packages/", {"tracking_code": "X"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_autodetect_carrier(self):
        resp = self.client.post(
            "/api/v1/packages/",
            {"tracking_code": "AM101610575BR"},
            format="json", **self.auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(Package.objects.get(tracking_code="AM101610575BR").carrier, "correios")

    def test_create_autodetect_rejects_unknown(self):
        resp = self.client.post(
            "/api/v1/packages/",
            {"tracking_code": "ZZZ999"},
            format="json", **self.auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertFalse(Package.objects.filter(tracking_code="ZZZ999").exists())

    def test_create_with_document_jt(self):
        resp = self.client.post(
            "/api/v1/packages/",
            {"tracking_code": "888030556767025", "document": "12345678901"},
            format="json", **self.auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        p = Package.objects.get(tracking_code="888030556767025")
        self.assertEqual(p.carrier, "jtexpress")
        self.assertEqual(p.document, "12345678901")
        self.assertNotIn("document", resp.data)

    def test_sync_action(self):
        Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        with mock.patch("apps.trackings.api.sync_package", return_value=True):
            resp = self.client.post(
                "/api/v1/packages/AM101610575BR/sync/",
                format="json", **self.auth(),
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertTrue(resp.data["sync_status"])
        self.assertEqual(resp.data["package"]["tracking_code"], "AM101610575BR")

    def test_list_and_retrieve(self):
        Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        resp = self.client.get("/api/v1/packages/", **self.auth())
        self.assertEqual(resp.status_code, 200)
        resp2 = self.client.get("/api/v1/packages/AM101610575BR/", **self.auth())
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.data["tracking_code"], "AM101610575BR")

    def test_detect_carrier_via_api(self):
        self.assertEqual(detect_carrier("AJ123456789"), "anjun")