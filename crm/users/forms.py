from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from crm.users.models import Role, UserProfile
from crm.zetom.models import DepartmentsVariants

# Базовый Tailwind стиль
INPUT_CLASS = "w-full px-3 py-2 rounded border border-gray-700 bg-gray-900 text-white"


class CustomUserCreateForm(forms.ModelForm):
    """Форма создания нового пользователя"""

    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS})
    )

    password_confirm = forms.CharField(
        label=_("Password confirmation"),
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS})
    )

    role = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        label=_("Role"),
        widget=forms.Select(attrs={"class": INPUT_CLASS})
    )

    departments = forms.MultipleChoiceField(
        choices=DepartmentsVariants.choices,
        label=_("Departments"),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": INPUT_CLASS})
    )

    job_title = forms.CharField(
        label=_("Job title"),
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS})
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
            raise forms.ValidationError(_("A user with this username already exists."))
        return username

    def clean_email(self):
        email = self.cleaned_data["email"]
        if not email:
            return email
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_("This email is already in use."))
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password")
        p2 = cleaned.get("password_confirm")

        if p1 and p2 and p1 != p2:
            raise forms.ValidationError(_("Passwords don't match."))

        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])

        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                role=self.cleaned_data["role"],
                departments=self.cleaned_data.get("departments") or [],
                job_title=self.cleaned_data.get("job_title") or None,
            )

        return user


class CustomUserChangeForm(forms.ModelForm):
    """Форма редактирования пользователя"""

    role = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        label=_("Role"),
        required=False,
        widget=forms.Select(attrs={"class": INPUT_CLASS})
    )

    job_title = forms.CharField(
        label=_("Job title"),
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS})
    )

    avatar = forms.ImageField(label=_("Avatar"), required=False)

    # claude — 2FA обязателен всем (crm.users.middleware.Enforce2FAMiddleware);
    # это единственная ручка, которой админ может отключить требование
    # конкретному юзеру (профиль.otp_exempt).
    otp_exempt = forms.BooleanField(
        label=_("2FA exempt"),
        required=False,
        help_text=_("If enabled, this user is not required to use two-factor authentication."),
    )

    # claude — поля смены пароля прямо в основной форме User'а, чтобы
    # Save во вкладке Security сабмитился вместе со всем остальным.
    new_password1 = forms.CharField(
        label=_("New password"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
        help_text=password_validation.password_validators_help_text_html(),
    )
    new_password2 = forms.CharField(
        label=_("New password confirmation"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
        help_text=_("Enter the same password as before, for verification."),
    )

    class Meta:
        model = User
        fields = [
            "username", "email", "first_name", "last_name",
            "is_active", "is_staff", "is_superuser",
        ]

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
            if profile.job_title:
                self.fields["job_title"].initial = profile.job_title
            self.fields["otp_exempt"].initial = profile.otp_exempt

    def clean_email(self):
        email = self.cleaned_data["email"]
        if not email:
            return email
        qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("This email is already in use."))
        return email

    # claude — валидация пары new_password1/new_password2:
    # пустые поля пропускаем (пароль не трогаем); если заполнены — проверяем
    # совпадение и крутим стандартные AUTH_PASSWORD_VALIDATORS.
    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1") or ""
        p2 = cleaned.get("new_password2") or ""
        if not p1 and not p2:
            return cleaned
        if p1 != p2:
            self.add_error("new_password2", _("The two password fields didn’t match."))
            return cleaned
        try:
            password_validation.validate_password(p1, self.instance)
        except forms.ValidationError as exc:
            self.add_error("new_password1", exc)
        return cleaned

    def save(self, commit=True):
        # claude — set_password перед super().save(), чтобы хеш записался
        # вместе с остальными полями User'а; пустой пароль = «не менять».
        new_password = self.cleaned_data.get("new_password1") or ""
        if new_password:
            self.instance.set_password(new_password)
        user = super().save(commit=commit)

        profile, _created = UserProfile.objects.get_or_create(user=user)
        role = self.cleaned_data.get("role")
        if role is not None:
            profile.role = role

        job_title = self.cleaned_data.get("job_title")
        if job_title:
            profile.job_title = job_title
        elif job_title == "":
            profile.job_title = None

        profile.otp_exempt = self.cleaned_data.get("otp_exempt", False)

        avatar = self.cleaned_data.get("avatar")
        if avatar:
            profile.avatar = avatar

        profile.save()
        return user


class UserProfileEditForm(forms.ModelForm):
    """Форма редактирования своего профиля (без роли)"""

    # claude — без widget тут рендерился голый нативный <input type="file">
    # (кнопка ОС + "файл не выбран"). class="hidden" + <label for=...> в
    # шаблоне (user_profile_edit.html) прячет его и заменяет кружком-
    # превью с оверлеем — сам input остаётся тем же полем формы, просто
    # невидимым триггером клика.
    avatar = forms.ImageField(
        label=_("Avatar"),
        required=False,
        widget=forms.FileInput(attrs={
            "class": "hidden",
            "accept": "image/*",
            "x-on:change": (
                "fileName = $event.target.files[0]?.name || '';"
                " preview = $event.target.files[0]"
                " ? URL.createObjectURL($event.target.files[0]) : null"
            ),
        }),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

        # claude — explicit autocomplete hints: without them Chrome's
        # autofill was mispredicting first_name's value from the filename
        # picked in the neighbouring avatar <input type="file"> (confirmed
        # via a native browser autofill write that bypasses JS entirely —
        # not something our own code triggers). Naming the field's real
        # purpose stops Chrome from guessing.
        widgets = {
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS, "autocomplete": "email"}),
            "first_name": forms.TextInput(attrs={"class": INPUT_CLASS, "autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"class": INPUT_CLASS, "autocomplete": "family-name"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"]
        if not email:
            return email
        qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("This email is already in use."))
        return email

    def save(self, commit=True):
        user = super().save(commit=commit)
        avatar = self.cleaned_data.get("avatar")
        if avatar:
            profile, _created = UserProfile.objects.get_or_create(user=user)
            profile.avatar = avatar
            profile.save(update_fields=["avatar"])
        return user
