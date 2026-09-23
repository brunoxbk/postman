from datetime import datetime

from django.test import SimpleTestCase

from apps.carriers.parsing import parse_datetime, parse_date, to_aware


class ParsingTestCase(SimpleTestCase):
    def test_iso_microseconds(self):
        dt = parse_datetime("2025-03-03 23:30:03.000000")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.date().isoformat(), "2025-03-03")

    def test_iso_plain(self):
        dt = parse_datetime("2025-05-28 13:33:27")
        self.assertEqual(dt.date().isoformat(), "2025-05-28")

    def test_unix_millis(self):
        dt = parse_datetime(1748410407000)
        self.assertEqual(dt.date().isoformat(), "2025-05-28")

    def test_unix_seconds(self):
        dt = parse_datetime(1749140169)
        self.assertEqual(dt.date().isoformat(), "2025-06-05")

    def test_day_first(self):
        dt = parse_datetime("21-01-2025 09:22:13")
        self.assertEqual(dt.date().isoformat(), "2025-01-21")

    def test_combined_date_time(self):
        dt = parse_datetime("2026-02-27 20:51:18")
        self.assertEqual(dt.date().isoformat(), "2026-02-27")

    def test_to_aware_naive(self):
        out = to_aware(datetime(2025, 3, 3, 23, 30, 3))
        self.assertEqual(out.utcoffset().total_seconds(), -3 * 3600)

    def test_date_dmy(self):
        self.assertEqual(parse_date("20/03/2025").isoformat(), "2025-03-20")

    def test_date_ymd(self):
        self.assertEqual(parse_date("2026-03-23").isoformat(), "2026-03-23")

    def test_none_safe(self):
        self.assertIsNone(parse_datetime(None))
        self.assertIsNone(parse_datetime(""))
        self.assertIsNone(parse_date(None))