# Django imports
from django import forms
# Other imports
from phonenumber_field.formfields import PhoneNumberField

# Client module import
from crm.clients.fields import ClientField
# claude
from crm.clients.validators import normalize_nip, validate_nip
# Zetom app imports
from crm.zetom.models import (
    Oferta, RequestMain, RequestNull, Wniosek, Zlecenie,
)


class TemplateForm(forms.ModelForm):
    # NEW FIELD
    client = ClientField()

    phone = PhoneNumberField(
        region="PL",
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "Phone"}),
    )

    company_name = forms.CharField(
        required=False, widget=forms.TextInput(attrs={"placeholder": "Zetom"})
    )

    email = forms.EmailField(
        required=True, widget=forms.TextInput(attrs={"placeholder": "email@gmail.com"})
    )

    # claude
    company_nip = forms.CharField(
        required=True,
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
        required=False,
        widget=forms.Textarea(
            attrs={
                "placeholder": "Long and very interesting note for noting your long and intresting text"
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
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["first_name"].widget.attrs.setdefault("placeholder", "John")
        self.fields["last_name"].widget.attrs.setdefault("placeholder", "Johnson")


class AddRequestFormMain(TemplateForm):
    address = forms.CharField(
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
        self.fields["first_name"].widget.attrs.setdefault("placeholder", "John")
        self.fields["last_name"].widget.attrs.setdefault("placeholder", "Johnson")


class AddOferta(TemplateForm):
    price = forms.DecimalField(
        required=False, widget=forms.NumberInput(attrs={"placeholder": "0"})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "placeholder": "Long and very interesting note for noting your long and intresting text",
            }
        ),
    )

    class Meta:
        model = Oferta
        fields = (
            "client",          # NEW
            "from_main",
            "phone",
            "email",
            "company_name",
            "company_nip",
            "price",
            "notes",
            "source",
        )


class AddZlecenie(TemplateForm):
    price = forms.DecimalField(
        required=False, widget=forms.NumberInput(attrs={"placeholder": "0"})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "placeholder": "Long and very interesting note for noting your long and intresting text",
            }
        ),
    )

    class Meta:
        model = Zlecenie
        fields = (
            "client",          # NEW
            "from_main",
            "phone",
            "email",
            "company_name",
            "company_nip",
            "price",
            "notes",
            "source",
        )


class AddWniosek(TemplateForm):
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "placeholder": "Long and very interesting note for noting your long and intresting text",
            }
        ),
    )

    class Meta:
        model = Wniosek
        fields = (
            "client",          # NEW
            "from_main",
            "phone",
            "email",
            "company_name",
            "company_nip",
            "notes",
            "source",
        )
