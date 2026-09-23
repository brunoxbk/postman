from django.test import TestCase

from apps.core.models import SyncLog


class SyncLogTestCase(TestCase):
    def test_increment_same_day(self):
        SyncLog.increment()
        SyncLog.increment()
        SyncLog.increment()
        self.assertEqual(SyncLog.count_today(), 3)

    def test_count_today_isolation(self):
        SyncLog.increment()
        self.assertEqual(SyncLog.count_today(), 1)