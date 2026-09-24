import threading
from unittest import skipUnless

from django.db import connection
from django.test import TestCase, TransactionTestCase

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
        self.assertEqual(SyncLog.count_today(), 100)