from django import forms
from crm.clients.models import Client


class ClientField(forms.ModelChoiceField):
    
    def __init__(self, *args, **kwargs):
        super().__init__(
            queryset=Client.objects.all(),
            required=False,
            label="Client",
            widget=forms.Select(attrs={"class": "form-control"}),
            *args,
            **kwargs
        )
