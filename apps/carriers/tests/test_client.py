from unittest import mock

import requests
from django.test import SimpleTestCase

from apps.carriers.client import PacoteVicioClient
from apps.carriers.exceptions import (
    PacoteVicioClientError,
    PacoteVicioServerError,
)

SESSION_GET = "apps.carriers.client.requests.Session.get"


class ClientTestCase(SimpleTestCase):
    def test_success_sends_v1_url_and_headers(self):
        resp = mock.Mock()
        resp.ok = True
        resp.status_code = 200
        resp.json.return_value = {"tracking_code": "X"}
        client = PacoteVicioClient()
        with mock.patch(SESSION_GET, return_value=resp) as get:
            data = client.fetch("correios", "AM101610575BR")
        url = get.call_args.args[0]
        self.assertIn("/v1/track/correios/AM101610575BR", url)
        self.assertIn("retry_level=high", url)
        self.assertEqual(data["tracking_code"], "X")

    def test_session_has_api_key_and_user_agent(self):
        client = PacoteVicioClient()
        self.assertEqual(client.session.headers.get("X-API-Key"), "")
        self.assertEqual(client.session.headers.get("User-Agent"), "postman/1.0")

    def test_jt_sends_tracking_document_header(self):
        resp = mock.Mock(ok=True, status_code=200, json=lambda: {"tracking_code": "Y"})
        client = PacoteVicioClient()
        with mock.patch(SESSION_GET, return_value=resp) as get:
            client.fetch("jtexpress", "888030556767025", document="12345678901")
        self.assertEqual(
            get.call_args.kwargs["headers"]["X-Tracking-Document"], "12345678901"
        )

    def test_no_document_means_no_tracking_document_header(self):
        resp = mock.Mock(ok=True, status_code=200, json=lambda: {"tracking_code": "Y"})
        client = PacoteVicioClient()
        with mock.patch(SESSION_GET, return_value=resp) as get:
            client.fetch("jtexpress", "888030556767025")
        self.assertNotIn("X-Tracking-Document", get.call_args.kwargs["headers"])

    def test_error_envelope_exposes_code(self):
        resp = mock.Mock(ok=False, status_code=404, text="{}")
        resp.json.return_value = {
            "error": {"code": "tracking_not_found", "message": "sem registro", "request_id": "abc"}
        }
        with mock.patch(SESSION_GET, return_value=resp):
            with self.assertRaises(PacoteVicioClientError) as ctx:
                PacoteVicioClient().fetch("correios", "AM101610575BR")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.code, "tracking_not_found")

    def test_auth_error_raises_client_error(self):
        resp = mock.Mock(ok=False, status_code=401, text="{}")
        resp.json.return_value = {"error": {"code": "invalid_api_key", "message": "chave inválida"}}
        with mock.patch(SESSION_GET, return_value=resp):
            with self.assertRaises(PacoteVicioClientError) as ctx:
                PacoteVicioClient().fetch("correios", "BR123456789BR")
        self.assertEqual(ctx.exception.code, "invalid_api_key")

    def test_server_error_raises(self):
        resp = mock.Mock(ok=False, status_code=500, text="boom")
        resp.json.return_value = {"error": {"code": "internal_error", "message": "falha nossa"}}
        with mock.patch(SESSION_GET, return_value=resp):
            import apps.carriers.client as client_mod
            with mock.patch.object(client_mod.time, "sleep"):
                with self.assertRaises(PacoteVicioServerError):
                    PacoteVicioClient().fetch("correios", "BR123456789BR")

    def test_retry_once_on_429_then_success(self):
        first = mock.Mock(ok=False, status_code=429, text="rate", json=lambda: None)
        second = mock.Mock(ok=True, status_code=200, json=lambda: {"ok": True})
        with mock.patch(SESSION_GET, side_effect=[first, second]) as get:
            import apps.carriers.client as client_mod
            with mock.patch.object(client_mod.time, "sleep"):
                data = PacoteVicioClient().fetch("correios", "BR123456789BR")
        self.assertEqual(get.call_count, 2)
        self.assertEqual(data, {"ok": True})

    def test_429_raises_after_retry(self):
        resp = mock.Mock(ok=False, status_code=429, text="rate")
        with mock.patch(SESSION_GET, return_value=resp) as get:
            import apps.carriers.client as client_mod
            with mock.patch.object(client_mod.time, "sleep"):
                with self.assertRaises(PacoteVicioServerError):
                    PacoteVicioClient().fetch("correios", "BR123456789BR")
        self.assertEqual(get.call_count, 2)

    def test_has_reusable_session(self):
        client = PacoteVicioClient()
        self.assertIsInstance(client.session, requests.Session)

    def test_shared_session_across_fetches(self):
        resp = mock.Mock(ok=True, status_code=200, json=lambda: {"ok": True})
        client = PacoteVicioClient()
        with mock.patch.object(client.session, "get", return_value=resp) as get:
            client.fetch("correios", "AM101610575BR")
            client.fetch("anjun", "AJ250101341570001")
        self.assertEqual(get.call_count, 2)

    def test_retry_respects_retry_after(self):
        first = mock.Mock(ok=False, status_code=429, text="rate", json=lambda: None)
        first.headers = {"Retry-After": "2"}
        second = mock.Mock(ok=True, status_code=200, json=lambda: {"ok": True})
        with mock.patch(SESSION_GET, side_effect=[first, second]) as get:
            import apps.carriers.client as client_mod
            with mock.patch.object(client_mod.time, "sleep") as sleep:
                PacoteVicioClient().fetch("correios", "BR123456789BR")
        sleep.assert_called_once_with(2)
        self.assertEqual(get.call_count, 2)