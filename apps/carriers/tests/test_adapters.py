import json
from pathlib import Path

from django.test import SimpleTestCase

from apps.carriers.adapters import (
    ADAPTERS,
    detect_carrier,
    get_adapter,
    is_plausible_code,
    normalize_v1,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads(FIXTURES.joinpath(name).read_text())


class AdaptersTestCase(SimpleTestCase):
    def test_all_registered(self):
        self.assertEqual(
            {"correios", "aliexpress", "shopee", "anjun", "jtexpress", "totalexpress"},
            set(ADAPTERS.keys()),
        )

    def test_jt_requires_document(self):
        self.assertTrue(get_adapter("jtexpress").requires_document)

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

    def test_is_plausible_code(self):
        for code in ("ZZZ999", "888002557196685", "BR2561249217932", "AMZB901884819tx"):
            self.assertTrue(is_plausible_code(code), code)
        for code in ("multimetro", "x", "", "12345", "A B C123", "código!!"):
            self.assertFalse(is_plausible_code(code), code)


class NormalizeV1TestCase(SimpleTestCase):
    def test_delivered_is_terminal(self):
        n = normalize_v1(load("v1_delivered.json"))
        self.assertEqual(n.tracking_code, "AM101610575BR")
        self.assertEqual(n.status_code, "delivered")
        self.assertEqual(n.status_label, "Entregue")
        self.assertTrue(n.is_terminal)
        self.assertEqual(n.terminal_state, "delivered")
        self.assertEqual(len(n.events), 3)
        self.assertEqual(n.events[-1].status_key, "delivered")
        self.assertEqual(n.events[-1].status_label, "Entregue")
        self.assertEqual(n.estimated_delivery.isoformat(), "2026-07-20")
        self.assertIsNotNone(n.last_event_at)

    def test_keeps_synthetic_attribution_event(self):
        n = normalize_v1(load("v1_delivered.json"))
        first = n.events[0]
        self.assertEqual(first.status_key, "unknown")
        self.assertEqual(first.status_label, "Rastreio fornecido por PacoteVicio.dev")
        self.assertEqual(first.location, "")

    def test_in_transit_not_terminal(self):
        n = normalize_v1(load("v1_in_transit.json"))
        self.assertFalse(n.is_terminal)
        self.assertIsNone(n.terminal_state)
        self.assertEqual(n.status_code, "in_transit")
        self.assertEqual(n.estimated_delivery.isoformat(), "2026-08-15")
        self.assertEqual(n.location, "Sao Paulo / SP")

    def test_location_builds_from_location_object(self):
        n = normalize_v1(load("v1_in_transit.json"))
        self.assertEqual(n.location, "Sao Paulo / SP")

    def test_exception_is_not_terminal(self):
        n = normalize_v1(load("v1_exception.json"))
        self.assertFalse(n.is_terminal)
        self.assertIsNone(n.terminal_state)
        self.assertEqual(n.events[-1].status_key, "exception")

    def test_returned_is_terminal_returned(self):
        raw = load("v1_delivered.json")
        raw["status"] = "returned"
        raw["delivered_at"] = None
        raw["status_updated_at"] = "2026-07-22T09:00:00Z"
        n = normalize_v1(raw)
        self.assertTrue(n.is_terminal)
        self.assertEqual(n.terminal_state, "returned")

    def test_empty_payload_is_not_terminal(self):
        n = normalize_v1({
            "tracking_code": "X", "courier": "correios", "status": "unknown",
            "status_updated_at": None, "events": [],
        })
        self.assertFalse(n.is_terminal)
        self.assertEqual(n.events, [])