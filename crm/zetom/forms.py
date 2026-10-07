# Django imports
from django import forms
from django.utils.translation import gettext_lazy as _
# Other imports
from phonenumber_field.formfields import PhoneNumberField

# Client module import
from crm.clients.fields import ClientField
# claude
from crm.clients.validators import normalize_nip, validate_nip
# Zetom app imports
from crm.zetom.models import (
    DepartmentsVariants, Oferta, RequestMain, RequestNull, Wniosek, Zlecenie,
)


# claude — Oferta/Zlecenie/Wniosek list "departments" in their ModelAdmin.fields
# without declaring it on the form (unlike price/notes/etc below), so Django
# auto-generates it from ArrayField.formfield() — that default is
# SimpleArrayField, a plain textarea expecting hand-typed comma-separated
# codes, with no indication of which codes are valid. Declared explicitly
# here (same pattern as elsewhere in this file) so it's a real multi-select
# instead; TypedMultipleChoiceField.clean() returns a plain list of strings,
# which is exactly what ArrayField stores — no widget/data-shape mismatch.
def _departments_field():
    return forms.TypedMultipleChoiceField(
        choices=DepartmentsVariants.choices,
        required=False,
        coerce=str,
        widget=forms.SelectMultiple,
    )


class TemplateForm(forms.ModelForm):
    # NEW FIELD
    client = ClientField()

    phone = PhoneNumberField(
        label=_("Phone"),
        region="PL",
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "+48 501 600 300"}),
    )

    company_name = forms.CharField(
        label=_("Company name"),
        required=False, widget=forms.TextInput(attrs={"placeholder": "Zetom"})
    )

    email = forms.EmailField(
        label=_("Email"),
        required=True, widget=forms.TextInput(attrs={"placeholder": "email@gmail.com"})
    )

    # claude
    company_nip = forms.CharField(
        required=False,
        max_length=20,
        validators=[validate_nip],
        widget=forms.TextInput(attrs={"placeholder": "7322215365"}),
    )

    # claude
    def clean_company_nip(self):
        value = self.cleaned_data.get("company_nip")
        if not value:
            return value
        return normalize_nip(value)

    message = forms.CharField(
        label=_("Message"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "placeholder": "Dodatkowe informacje lub uwagi dotyczące zgłoszenia"
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})


class AddRequestFormNull(TemplateForm):
    class Meta:
        model = RequestNull
        fields = (
            "client",          # NEW
            "first_name",
            "last_name",
           "phone",
            "email",
            "company_name",
            "message",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("company_nip", None)
        # claude — Django admin drops editable fields from self.fields for a
        # view-only user (no change permission), so these keys don't always
        # exist; unconditional access 500'd for e.g. the read-only auditor role.
        if "first_name" in self.fields:
            self.fields["first_name"].required = True
            self.fields["first_name"].widget.attrs.setdefault("placeholder", "Jan")
        if "last_name" in self.fields:
            self.fields["last_name"].required = True
            self.fields["last_name"].widget.attrs.setdefault("placeholder", "Kowalski")


class AddRequestFormMain(TemplateForm):
    address = forms.CharField(
        label=_("Address"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "placeholder": "ulica Gen. Jozefa Hallera 76/49",
                "rows": 2,
            }
        ),
    )

    class Meta:
        model = RequestMain
        fields = (
            "client",          # NEW
            "first_name",
            "last_name",
            "phone",
            "company_name",
            "email",
            "company_nip",
            "address",
            "message",
            "source",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "first_name" in self.fields:
            self.fields["first_name"].widget.attrs.setdefault("placeholder", "Jan")
        if "last_name" in self.fields:
            self.fields["last_name"].widget.attrs.setdefault("placeholder", "Kowalski")


class AddOferta(TemplateForm):
    departments = _departments_field()
    price = forms.DecimalField(
        required=False, widget=forms.NumberInput(attrs={"placeholder": "0"})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "placeholder": "Dodatkowe informacje lub uwagi dotyczące zgłoszenia",
            }
        ),
    )

    class Meta:
        model = Oferta
        fields = (
            "client",          # NEW
            "from_main",
            "phone",
            "departments",
            "email",
            "company_name",
            "company_nip",
            "price",
            "notes",
            "source",
        )


class AddZlecenie(TemplateForm):
    departments = _departments_field()
    price = forms.DecimalField(
        required=False, widget=forms.NumberInput(attrs={"placeholder": "0"})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "placeholder": "Dodatkowe informacje lub uwagi dotyczące zgłoszenia",
            }
        ),
    )

    class Meta:
        model = Zlecenie
        fields = (
            "client",          # NEW
            "from_main",
            "phone",
            "departments",
            "email",
            "company_name",
            "company_nip",
            "price",
            "notes",
            "source",
        )


class AddWniosek(TemplateForm):
    departments = _departments_field()
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "placeholder": "Dodatkowe informacje lub uwagi dotyczące zgłoszenia",
            }
        ),
    )

    class Meta:
        model = Wniosek
        fields = (
            "client",          # NEW
            "from_main",
            "phone",
            "departments",
            "email",
            "company_name",
            "company_nip",
            "notes",
            "source",
        )
