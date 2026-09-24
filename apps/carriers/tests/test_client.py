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
    def test_success(self):
        resp = mock.Mock()
        resp.ok = True
        resp.status_code = 200
        resp.json.return_value = {"codObjeto": "X"}
        with mock.patch(SESSION_GET, return_value=resp) as get:
            client = PacoteVicioClient()
            data = client.fetch("/correios", {"tracking_code": "AM101610575BR"})
        get.assert_called_once()
        self.assertEqual(data["codObjeto"], "X")

    def test_client_error_raises(self):
        resp = mock.Mock()
        resp.ok = False
        resp.status_code = 401
        resp.text = "unauthorized"
        with mock.patch(SESSION_GET, return_value=resp):
            client = PacoteVicioClient()
            with self.assertRaises(PacoteVicioClientError):
                client.fetch("/correios", {"tracking_code": "X"})

    def test_server_error_raises(self):
        resp = mock.Mock()
        resp.ok = False
        resp.status_code = 500
        resp.text = "boom"
        with mock.patch(SESSION_GET, return_value=resp):
            with self.assertRaises(PacoteVicioServerError):
                PacoteVicioClient().fetch("/correios", {"tracking_code": "X"})

    def test_retry_once_on_429_then_success(self):
        first = mock.Mock(ok=False, status_code=429, text="rate", json=lambda: None)
        second = mock.Mock(ok=True, status_code=200, json=lambda: {"ok": True})
        with mock.patch(SESSION_GET, side_effect=[first, second]) as get:
            import apps.carriers.client as client_mod
            with mock.patch.object(client_mod.time, "sleep"):
                data = PacoteVicioClient().fetch("/correios", {"tracking_code": "X"})
        self.assertEqual(get.call_count, 2)
        self.assertEqual(data, {"ok": True})

    def test_429_raises_after_retry(self):
        resp = mock.Mock(ok=False, status_code=429, text="rate")
        with mock.patch(SESSION_GET, return_value=resp) as get:
            import apps.carriers.client as client_mod
            with mock.patch.object(client_mod.time, "sleep"):
                with self.assertRaises(PacoteVicioServerError):
                    PacoteVicioClient().fetch("/correios", {"tracking_code": "X"})
        self.assertEqual(get.call_count, 2)

    def test_has_reusable_session(self):
        client = PacoteVicioClient()
        self.assertIsInstance(client.session, requests.Session)

    def test_shared_session_across_fetches(self):
        resp = mock.Mock(ok=True, status_code=200, json=lambda: {"ok": True})
        client = PacoteVicioClient()
        with mock.patch.object(client.session, "get", return_value=resp) as get:
            client.fetch("/correios", {"tracking_code": "X"})
            client.fetch("/anjun", {"tracking_code": "Y"})
        self.assertEqual(get.call_count, 2)