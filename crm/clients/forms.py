# claude
"""Inline-edit form for the custom Client Detail (change_form) screen.

Plain ModelForm bound to the identity card. The template renders the widgets
by hand (read/edit toggle), so widgets only carry the CSS classes the
stylesheet expects. client_type is a radio so switching it flips which
fieldset the card shows.
"""
from django import forms

from crm.clients.models import Client, ClientType
# claude
from crm.clients.validators import normalize_nip, validate_nip


class ClientForm(forms.ModelForm):
    # claude — explicit form-level NIP validation mirrors TemplateForm/RequestMain
    def clean_company_nip(self):
        value = self.cleaned_data.get("company_nip")
        if not value:
            return value
        validate_nip(value)
        return normalize_nip(value)

    class Meta:
        model = Client
        fields = [
            "client_type",
            "first_name", "last_name",
            "company_name", "company_nip",
            "phone", "email",
            "notes",
        ]
        widgets = {
            "client_type": forms.RadioSelect(choices=ClientType.choices),
            "first_name": forms.TextInput(attrs={"class": "input"}),
            "last_name": forms.TextInput(attrs={"class": "input"}),
            "company_name": forms.TextInput(attrs={"class": "input"}),
            "company_nip": forms.TextInput(attrs={"class": "input mono", "placeholder": "PL XXXXXXXXXX"}),
            "phone": forms.TextInput(attrs={"class": "input mono"}),
            "email": forms.TextInput(attrs={"class": "input mono"}),
            "notes": forms.Textarea(attrs={"class": "textarea"}),
        }
