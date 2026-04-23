# Django imports
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

# Other imports
from localflavor.pl.forms import PLNIPField
from phonenumber_field.formfields import PhoneNumberField

# Zetom app imports
from crm.zetom.models import Oferta, RequestMain, RequestNull, RequestTemplate, Zlecenie, Wniosek


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        label="",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Email Address"}
        ),
    )
    first_name = forms.CharField(
        label="",
        max_length=100,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "First Name"}
        ),
    )
    last_name = forms.CharField(
        label="",
        max_length=100,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Last Name"}
        ),
    )

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
        )

    def __init__(self, *args, **kwargs):
        super(SignUpForm, self).__init__(*args, **kwargs)

        self.fields["username"].widget.attrs["class"] = "form-control"
        self.fields["username"].widget.attrs["placeholder"] = "User Name"
        self.fields["username"].label = ""
        self.fields["username"].help_text = (
            '<span class="form-text text-muted"><small>Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.</small></span>'
        )

        self.fields["password1"].widget.attrs["class"] = "form-control"
        self.fields["password1"].widget.attrs["placeholder"] = "Password"
        self.fields["password1"].label = ""
        self.fields["password1"].help_text = (
            "<ul class=\"form-text text-muted small\"><li>Your password can't be too similar to your other personal information.</li><li>Your password must contain at least 8 characters.</li><li>Your password can't be a commonly used password.</li><li>Your password can't be entirely numeric.</li></ul>"
        )

        self.fields["password2"].widget.attrs["class"] = "form-control"
        self.fields["password2"].widget.attrs["placeholder"] = "Confirm Password"
        self.fields["password2"].label = ""
        self.fields["password2"].help_text = (
            '<span class="form-text text-muted"><small>Enter the same password as before, for verification.</small></span>'
        )


class TemplateForm(forms.ModelForm):
    phone = PhoneNumberField(
        region="PL",
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "Phone"}),
    )

    company_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Zetom"})
    )

    email = forms.EmailField(
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "email@gmail.com"})
    )

    company_nip = PLNIPField(
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "7322215365"}) # почему работает? - работающий NIP 7322215365
    )
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"placeholder": "Long and very interesting note for noting your long and intresting text" })
    )

    "Разобраться все еще как работает, но есть понимание что делает"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})


class AddRequestFormNull(TemplateForm):
    class Meta:
        model = RequestNull
        fields = ("phone", "company_name", "email", "company_nip", "message")


class AddRequestFormMain(TemplateForm):
    full_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "John Johnson"})
    )
    address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "placeholder": "ulica Gen. Jozefa Hallera 76/49",
            "rows": 2,
            })
    )

    class Meta:
        model = RequestMain
        fields = (
            "phone",
            "company_name",
            "email",
            "company_nip",
            "full_name",
            "address",
            "message",
        )


class AddOferta(TemplateForm):
    price = forms.DecimalField(required=False, widget=forms.NumberInput(attrs={"placeholder": "0"}))
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "placeholder": "Long and very interesting note for noting your long and intresting text",
            }
        )
    )
    class Meta:
        model = Oferta
        fields = ("from_main", "phone", "email", "company_name", "company_nip", "price", "notes")


class AddZlecenie(TemplateForm):
    price = forms.DecimalField(required=False, widget=forms.NumberInput(attrs={"placeholder": "0"}))
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "placeholder": "Long and very interesting note for noting your long and intresting text",
            }
        )
    )
    class Meta:
        model = Zlecenie
        fields = ("from_main", "phone", "email", "company_name", "company_nip", "price", "notes")


class AddWniosek(TemplateForm):
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "placeholder": "Long and very interesting note for noting your long and intresting text",
            }
        )
    )
    class Meta:
        model = Wniosek
        fields = ("from_main", "phone", "email", "company_name", "company_nip", "notes")
