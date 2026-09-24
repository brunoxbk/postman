import threading
from unittest import skipUnless

from django.db import connection
from django.test import TestCase, TransactionTestCase

from apps.core.models import SyncLog


class SyncLogTestCase(TestCase):
    def test_increment_same_month(self):
        SyncLog.increment()
        SyncLog.increment()
        SyncLog.increment()
        self.assertEqual(SyncLog.count_period(), 3)

    def test_count_period_isolation(self):
        SyncLog.increment()
        self.assertEqual(SyncLog.count_period(), 1)

    def test_month_row_is_first_day_of_month(self):
        SyncLog.increment()
        row = SyncLog._row()
        self.assertEqual(row.month.day, 1)

    def test_is_paused_when_quota_limit_reached(self):
        self.assertFalse(SyncLog.is_paused())
        row = SyncLog._row()
        SyncLog.objects.filter(pk=row.pk).update(requests=row.quota_limit)
        self.assertTrue(SyncLog.is_paused())


@skipUnless(connection.vendor == "postgresql", "Concorrência exige Postgres (sqlite em memória trava em escritas paralelas)")
class SyncLogConcurrentTestCase(TransactionTestCase):
    def test_increment_concurrent_no_lost_updates(self):
        def bump():
            for _ in range(20):
                SyncLog.increment()

        threads = [threading.Thread(target=bump) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(SyncLog.count_period(), 100)