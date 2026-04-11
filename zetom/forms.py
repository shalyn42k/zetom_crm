from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from localflavor.pl.forms import PLNIPField

# Библиотеки валидации номера и нипа
from phonenumber_field.formfields import PhoneNumberField

# Наши импорты
from .models import Oferta, RequestMain, RequestNull, RequestTemplate


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
        widget=forms.TextInput(attrs={"placeholder": "Phone", "class": "form-control"}),
    )

    company_name = forms.CharField(
        widget=forms.TextInput(attrs={"placeholder": "Zetom", "class": "form-control"})
    )

    email = forms.EmailField(
        widget=forms.TextInput(
            attrs={"placeholder": "email@gmail.com", "class": "form-control"}
        )
    )

    company_nip = PLNIPField(  # почему работает? - работающий NIP 7322215365
        widget=forms.TextInput(
            attrs={"placeholder": "1234567890", "class": "form-control"}
        )
    )


class AddRequestFormNull(TemplateForm):
    class Meta:
        model = RequestNull
        fields = ("phone", "company_name", "email", "company_nip")


class AddRequestFormMain(TemplateForm):
    full_name = forms.CharField(
        widget=forms.TextInput(
            attrs={"placeholder": "John Johnson", "class": "form-control"}
        )
    )
    address = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "placeholder": "ulica Gen. Jozefa Hallera 76/49",
                "class": "form-control",
            }
        )
    )
    notes = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "placeholder": "Long and very interesting note for noting your long and intresting text",
                "class": "form-control",
            }
        )
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
            "notes",
        )


class AddOferta(AddRequestFormMain):
    price = forms.DecimalField(
        widget=forms.NumberInput(attrs={"placeholder": "0.00", "class": "form-control"})
    )

    class Meta:
        model = Oferta
        fields = ("company_name", "company_nip", "full_name", "price")
