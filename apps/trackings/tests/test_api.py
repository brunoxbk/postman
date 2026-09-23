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

    def test_list_and_retrieve(self):
        Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        resp = self.client.get("/api/v1/packages/", **self.auth())
        self.assertEqual(resp.status_code, 200)
        resp2 = self.client.get("/api/v1/packages/AM101610575BR/", **self.auth())
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.data["tracking_code"], "AM101610575BR")

    def test_detect_carrier_via_api(self):
        self.assertEqual(detect_carrier("AJ123456789"), "anjun")