from django import forms

from apps.carriers.adapters import detect_carrier
from apps.carriers.constants import CARRIER_CHOICES
from apps.trackings.models import Package


class PackageForm(forms.ModelForm):
    carrier = forms.ChoiceField(choices=CARRIER_CHOICES, required=False, label="Transportadora (automática)")

    class Meta:
        model = Package
        fields = ["tracking_code", "label", "carrier", "document"]
        widgets = {
            "tracking_code": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "label": forms.TextInput(attrs={"class": "form-control"}),
            "document": forms.TextInput(attrs={"class": "form-control", "placeholder": "Somente dígitos"}),
        }

    def __init__(self, *args, **kwargs):
        self._original_code = None
        instance = kwargs.get("instance")
        if instance is not None:
            self._original_code = instance.tracking_code
        super().__init__(*args, **kwargs)

    def clean_tracking_code(self):
        return self.cleaned_data["tracking_code"].strip()

    def clean(self):
        cleaned = super().clean()
        code = cleaned.get("tracking_code")
        carrier = cleaned.get("carrier")
        detected = detect_carrier(code) if code else None
        if not carrier:
            if not detected:
                raise forms.ValidationError(
                    {"tracking_code": "Não foi possível identificar a transportadora pelo código."}
                )
            cleaned["carrier"] = detected
        elif self._original_code and code != self._original_code and detected:
            cleaned["carrier"] = detected
        return cleaned

    def clean_document(self):
        doc = self.cleaned_data.get("document") or ""
        digits = "".join(ch for ch in doc if ch.isdigit())
        carrier = self.cleaned_data.get("carrier") or detect_carrier(self.cleaned_data.get("tracking_code", "")) or ""
        if carrier == "jtexpress" and len(digits) != 11:
            raise forms.ValidationError("CPF do destinatário deve ter 11 dígitos (J&T Express).")
        return digits

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.carrier:
            instance.carrier = detect_carrier(instance.tracking_code)
        if commit:
            instance.save()
        return instance