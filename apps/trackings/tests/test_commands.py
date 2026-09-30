import io
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

SYNC_ALL = "apps.trackings.management.commands.sync_trackings.sync_all"

OK = {"ok": 2, "erro": 0, "pausado": 0, "sem_documento": 0}
WITH_ERROR = {"ok": 1, "erro": 1, "pausado": 0, "sem_documento": 0}
WITH_PAUSED = {"ok": 1, "erro": 0, "pausado": 1, "sem_documento": 0}


class SyncTrackingsCommandTestCase(TestCase):
    def test_run_prints_totals(self):
        out = io.StringIO()
        with mock.patch(SYNC_ALL, return_value=OK):
            call_command("sync_trackings", stdout=out)
        self.assertIn("ok: 2", out.getvalue())
        self.assertIn("====", out.getvalue())

    def test_run_quiet_omits_headers(self):
        out = io.StringIO()
        with mock.patch(SYNC_ALL, return_value=OK):
            call_command("sync_trackings", quiet=True, stdout=out)
        self.assertIn("ok: 2", out.getvalue())
        self.assertNotIn("====", out.getvalue())

    def test_error_raises_command_error(self):
        with mock.patch(SYNC_ALL, return_value=WITH_ERROR):
            with self.assertRaises(CommandError):
                call_command("sync_trackings")

    def test_paused_raises_command_error(self):
        with mock.patch(SYNC_ALL, return_value=WITH_PAUSED):
            with self.assertRaises(CommandError):
                call_command("sync_trackings")

    def test_run_force_passes_force_to_sync_all(self):
        with mock.patch(SYNC_ALL, return_value=OK) as mock_sync_all:
            call_command("sync_trackings", force=True, quiet=True)
            mock_sync_all.assert_called_once_with(force=True)