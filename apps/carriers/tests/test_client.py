from unittest import mock

from django.test import SimpleTestCase

from apps.carriers.client import PacoteVicioClient
from apps.carriers.exceptions import (
    PacoteVicioClientError,
    PacoteVicioServerError,
)


class ClientTestCase(SimpleTestCase):
    def test_success(self):
        resp = mock.Mock()
        resp.ok = True
        resp.status_code = 200
        resp.json.return_value = {"codObjeto": "X"}
        with mock.patch("apps.carriers.client.requests.get", return_value=resp) as get:
            client = PacoteVicioClient()
            data = client.fetch("/correios", {"tracking_code": "AM101610575BR"})
        get.assert_called_once()
        self.assertEqual(data["codObjeto"], "X")

    def test_client_error_raises(self):
        resp = mock.Mock()
        resp.ok = False
        resp.status_code = 401
        resp.text = "unauthorized"
        with mock.patch("apps.carriers.client.requests.get", return_value=resp):
            client = PacoteVicioClient()
            with self.assertRaises(PacoteVicioClientError):
                client.fetch("/correios", {"tracking_code": "X"})

    def test_server_error_raises(self):
        resp = mock.Mock()
        resp.ok = False
        resp.status_code = 500
        resp.text = "boom"
        with mock.patch("apps.carriers.client.requests.get", return_value=resp):
            with self.assertRaises(PacoteVicioServerError):
                PacoteVicioClient().fetch("/correios", {"tracking_code": "X"})