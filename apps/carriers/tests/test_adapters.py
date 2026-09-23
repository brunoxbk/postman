import json
from pathlib import Path

from django.test import SimpleTestCase

from apps.carriers.adapters import ADAPTERS, detect_carrier, get_adapter

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads(FIXTURES.joinpath(name).read_text())


class AdaptersTestCase(SimpleTestCase):
    def test_all_registered(self):
        self.assertEqual(
            {"correios", "aliexpress", "shopee", "anjun", "jtexpress", "totalexpress"},
            set(ADAPTERS.keys()),
        )

    def test_correios_normalize(self):
        raw = load("correios.json")
        n = get_adapter("correios").normalize(raw)
        self.assertEqual(n.tracking_code, "AM101610575BR")
        self.assertTrue(n.is_terminal)
        self.assertEqual(n.status_label, "ENTREGUE")
        self.assertEqual(len(n.events), 2)
        self.assertEqual(n.events[0].status_key, "BDE")

    def test_aliexpress_normalize(self):
        n = get_adapter("aliexpress").normalize(load("aliexpress.json"))
        self.assertIsNotNone(n.last_event_at)
        self.assertIsNotNone(n.estimated_delivery)

    def test_shopee_normalize(self):
        n = get_adapter("shopee").normalize(load("shopee.json"))
        self.assertEqual(n.status_code, "Delivered")
        self.assertTrue(n.is_terminal)
        self.assertEqual(len(n.events), 8)

    def test_anjun_normalize(self):
        n = get_adapter("anjun").normalize(load("anjun.json"))
        self.assertEqual(n.tracking_code, "AJ250101341570001")
        self.assertTrue(n.is_terminal)

    def test_jtexpress_normalize(self):
        n = get_adapter("jtexpress").normalize(load("jtexpress.json"))
        self.assertEqual(n.status_code, "100")
        self.assertTrue(n.is_terminal)

    def test_totalexpress_normalize(self):
        n = get_adapter("totalexpress").normalize(load("totalexpress.json"))
        self.assertEqual(n.tracking_code, "AMZB901884819tx")
        self.assertTrue(n.is_terminal)
        self.assertEqual(len(n.events), 7)
        self.assertEqual(n.estimated_delivery.isoformat(), "2026-03-23")

    def test_detect(self):
        cases = [
            ("AM101610575BR", "correios"),
            ("LP00123456789CN", "aliexpress"),
            ("BR2561249217932", "shopee"),
            ("AJ250101341570001", "anjun"),
            ("888030556767025", "jtexpress"),
            ("AMZB901884819tx", "totalexpress"),
            ("ZZ999999999BX", None),
        ]
        for code, expected in cases:
            self.assertEqual(detect_carrier(code), expected, code)


class JTAdapterTestCase(SimpleTestCase):
    def test_requires_document(self):
        self.assertTrue(get_adapter("jtexpress").requires_document)

    def test_build_params_with_document(self):
        params = get_adapter("jtexpress").build_params("888030556767025", "12345678901")
        self.assertEqual(params["document"], "12345678901")
        self.assertEqual(params["tracking_code"], "888030556767025")