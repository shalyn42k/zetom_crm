from django import forms
from django.contrib.auth.models import User

from crm.users.models import Role, UserProfile
from crm.zetom.models import DepartmentsVariants

# Базовый Tailwind стиль
INPUT_CLASS = "w-full px-3 py-2 rounded border border-gray-700 bg-gray-900 text-white"


class CustomUserCreateForm(forms.ModelForm):
    """Форма создания нового пользователя"""

    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS})
    )

    password_confirm = forms.CharField(
        label="Подтверждение пароля",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS})
    )

    role = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        label="Роль",
        widget=forms.Select(attrs={"class": INPUT_CLASS})
    )

    department = forms.ChoiceField(
        choices=DepartmentsVariants.choices,
        label="Департамент",
        required=False,
        widget=forms.Select(attrs={"class": INPUT_CLASS})
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]

        widgets = {
            "username": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS}),
            "first_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "last_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
        }

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Пользователь с таким username уже существует.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Email уже используется.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password")
        p2 = cleaned.get("password_confirm")

        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Пароли не совпадают.")

        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])

        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                role=self.cleaned_data["role"],
                department=self.cleaned_data.get("department") or None
            )

        return user


class CustomUserChangeForm(forms.ModelForm):
    """Форма редактирования пользователя"""

    role = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        label="Роль",
        required=False,
        widget=forms.Select(attrs={"class": INPUT_CLASS})
    )

    department = forms.ChoiceField(
        choices=[("", "---")] + list(DepartmentsVariants.choices),
        label="Департамент",
        required=False,
        widget=forms.Select(attrs={"class": INPUT_CLASS})
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]

        widgets = {
            "username": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS}),
            "first_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "last_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = getattr(self.instance, "profile", None)
        if profile:
            if profile.role:
                self.fields["role"].initial = profile.role
            if profile.department:
                self.fields["department"].initial = profile.department

    def clean_email(self):
        email = self.cleaned_data["email"]
        qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Email уже используется.")
        return email

    def save(self, commit=True):
        user = super().save(commit=commit)

        profile, _ = UserProfile.objects.get_or_create(user=user)
        role = self.cleaned_data.get("role")
        if role is not None:
            profile.role = role

        department = self.cleaned_data.get("department")
        if department:
            profile.department = department
        elif department == "":
            profile.department = None

        profile.save()
        return user


class UserProfileEditForm(forms.ModelForm):
    """Форма редактирования своего профиля (без роли)"""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

        widgets = {
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS}),
            "first_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "last_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"]
        qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Email уже используется.")
        return email
