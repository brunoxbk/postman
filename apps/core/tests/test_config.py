from django.conf import settings
from django.test import SimpleTestCase


class ConfigTestCase(SimpleTestCase):
    def test_language_pt_br(self):
        self.assertEqual(settings.LANGUAGE_CODE, "pt-br")

    def test_timezone_sao_paulo(self):
        self.assertEqual(settings.TIME_ZONE, "America/Sao_Paulo")