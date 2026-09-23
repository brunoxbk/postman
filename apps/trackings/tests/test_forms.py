from django.test import TestCase

from apps.carriers.constants import CARRIER_CORREIOS, CARRIER_SHOPEE
from apps.trackings.forms import PackageForm
from apps.trackings.models import Package


class PackageFormTestCase(TestCase):
    def test_autodetect_when_carrier_empty(self):
        form = PackageForm({"tracking_code": "AM101610575BR", "label": ""})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["carrier"], "correios")

    def test_manual_carrier_overrides_detection(self):
        form = PackageForm({
            "tracking_code": "LP123456789CN",
            "label": "",
            "carrier": CARRIER_CORREIOS,
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["carrier"], "correios")

    def test_requires_detection_without_carrier(self):
        form = PackageForm({"tracking_code": "ZZZ999", "label": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("tracking_code", form.errors)

    def test_manual_carrier_allows_unknown_code(self):
        form = PackageForm({
            "tracking_code": "ZZZ999",
            "label": "",
            "carrier": CARRIER_CORREIOS,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_edit_re_detects_when_code_changed(self):
        p = Package.objects.create(tracking_code="X1", carrier=CARRIER_CORREIOS)
        form = PackageForm({
            "tracking_code": "BR2561249217932",
            "label": "",
            "carrier": CARRIER_CORREIOS,
        }, instance=p)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["carrier"], CARRIER_SHOPEE)

    def test_edit_keeps_carrier_when_code_unchanged(self):
        p = Package.objects.create(tracking_code="X1", carrier=CARRIER_CORREIOS)
        form = PackageForm({
            "tracking_code": "X1",
            "label": "Novo rótulo",
            "carrier": CARRIER_CORREIOS,
        }, instance=p)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["carrier"], CARRIER_CORREIOS)