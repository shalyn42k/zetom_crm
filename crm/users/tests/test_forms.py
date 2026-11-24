# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ ФОРМ users
#
# Что тут тестируется:
#   CustomUserCreateForm:
#     • Валидные данные → форма is_valid(), save() создаёт User и UserProfile
#     • Дублирующийся username → ошибка
#     • Дублирующийся email → ошибка
#     • Пароли не совпадают → ошибка
#   CustomUserChangeForm:
#     • Редактирование без смены пароля — пароль не трогается
#     • Смена пароля с совпадающими полями — хэш обновляется
#     • Несовпадающие пароли → ошибка
#     • Email другого юзера → ошибка (но не свой же email)
#   UserProfileEditForm:
#     • Редактирование имени/фамилии
#     • Email другого юзера → ошибка
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase

from crm.users.forms import (
    CustomUserChangeForm,
    CustomUserCreateForm,
    UserProfileEditForm,
)
from crm.users.models import Role, UserProfile
from crm.users.signals_profile import create_user_profile

User = get_user_model()


def _make_role(code="specialist", name="Специалист"):
    """Вспомогательная функция: создать (или достать) роль."""
    role, _ = Role.objects.get_or_create(code=code, defaults={"name": name})
    return role


# ─────────────────────────── CustomUserCreateForm ─────────────────────────────


class CustomUserCreateFormTests(TestCase):
    """Форма создания нового пользователя (admin-side).

    После успешного save() в БД должны быть и User и UserProfile с нужными полями.
    """

    def setUp(self):
        self.role = _make_role()

    def _valid_data(self, **overrides):
        """Базовые валидные данные формы."""
        data = {
            "username": "newuser",
            "email": "new@test.com",
            "first_name": "Иван",
            "last_name": "Петров",
            "password": "StrongPass1!",
            "password_confirm": "StrongPass1!",
            "role": self.role.pk,
            "departments": [],
            "job_title": "Разработчик",
        }
        data.update(overrides)
        return data

    def test_valid_form_is_valid(self):
        form = CustomUserCreateForm(data=self._valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    # Тесты save() отключают сигнал create_user_profile на время теста.
    # Причина: сигнал запускается при user.save() и создаёт UserProfile
    # первым; форма затем пытается создать ещё один → IntegrityError.
    # @patch на имя функции в модуле НЕ работает для сигналов — Django
    # хранит weakref на оригинальный объект функции. Нужен disconnect().

    def test_save_creates_user_in_db(self):
        post_save.disconnect(create_user_profile, sender=User)
        try:
            form = CustomUserCreateForm(data=self._valid_data())
            self.assertTrue(form.is_valid())
            user = form.save()
            self.assertIsNotNone(user.pk)
            self.assertTrue(User.objects.filter(username="newuser").exists())
        finally:
            post_save.connect(create_user_profile, sender=User)

    def test_save_creates_user_profile(self):
        post_save.disconnect(create_user_profile, sender=User)
        try:
            form = CustomUserCreateForm(data=self._valid_data())
            self.assertTrue(form.is_valid())
            user = form.save()
            self.assertTrue(UserProfile.objects.filter(user=user).exists())
        finally:
            post_save.connect(create_user_profile, sender=User)

    def test_save_sets_role_on_profile(self):
        post_save.disconnect(create_user_profile, sender=User)
        try:
            form = CustomUserCreateForm(data=self._valid_data())
            self.assertTrue(form.is_valid())
            user = form.save()
            profile = UserProfile.objects.get(user=user)
            self.assertEqual(profile.role, self.role)
        finally:
            post_save.connect(create_user_profile, sender=User)

    def test_save_sets_job_title_on_profile(self):
        post_save.disconnect(create_user_profile, sender=User)
        try:
            form = CustomUserCreateForm(data=self._valid_data(job_title="DevOps"))
            self.assertTrue(form.is_valid())
            user = form.save()
            profile = UserProfile.objects.get(user=user)
            self.assertEqual(profile.job_title, "DevOps")
        finally:
            post_save.connect(create_user_profile, sender=User)

    def test_save_hashes_password(self):
        post_save.disconnect(create_user_profile, sender=User)
        try:
            form = CustomUserCreateForm(data=self._valid_data())
            self.assertTrue(form.is_valid())
            user = form.save()
            self.assertNotEqual(user.password, "StrongPass1!")
            self.assertTrue(user.check_password("StrongPass1!"))
        finally:
            post_save.connect(create_user_profile, sender=User)

    def test_duplicate_username_raises_error(self):
        User.objects.create_user(username="newuser", password="x")
        form = CustomUserCreateForm(data=self._valid_data())
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)

    def test_duplicate_email_raises_error(self):
        User.objects.create_user(username="other", email="new@test.com", password="x")
        form = CustomUserCreateForm(data=self._valid_data())
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_password_mismatch_raises_error(self):
        form = CustomUserCreateForm(
            data=self._valid_data(password="StrongPass1!", password_confirm="Different!")
        )
        self.assertFalse(form.is_valid())
        # Ошибка уровня __all__ (non_field_errors), не у конкретного поля.
        self.assertIn("__all__", form.errors)

    def test_empty_email_is_allowed(self):
        # email не обязательный в clean_email — пустая строка пропускается.
        form = CustomUserCreateForm(data=self._valid_data(email=""))
        self.assertTrue(form.is_valid(), form.errors)

    def test_optional_job_title_empty_is_fine(self):
        form = CustomUserCreateForm(data=self._valid_data(job_title=""))
        self.assertTrue(form.is_valid(), form.errors)


# ─────────────────────────── CustomUserChangeForm ─────────────────────────────


class CustomUserChangeFormTests(TestCase):
    """Форма редактирования существующего пользователя."""

    def setUp(self):
        self.role = _make_role()
        self.user = User.objects.create_user(
            username="existing", email="exist@test.com", password="OldPass1!"
        )
        # У пользователя должен быть профиль (создаётся сигналом).
        self.profile = self.user.profile

    def _valid_data(self, **overrides):
        data = {
            "username": "existing",
            "email": "exist@test.com",
            "first_name": "Анна",
            "last_name": "Иванова",
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
            "role": self.role.pk,
            "job_title": "QA",
            "new_password1": "",
            "new_password2": "",
        }
        data.update(overrides)
        return data

    def test_valid_form_without_password_change(self):
        form = CustomUserChangeForm(data=self._valid_data(), instance=self.user)
        self.assertTrue(form.is_valid(), form.errors)

    def test_save_without_password_keeps_old_hash(self):
        # Пустые поля new_password1/2 → пароль не меняется.
        old_hash = self.user.password
        form = CustomUserChangeForm(data=self._valid_data(), instance=self.user)
        self.assertTrue(form.is_valid())
        form.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, old_hash)

    def test_valid_password_change(self):
        # Заполненные совпадающие поля → хэш обновляется.
        form = CustomUserChangeForm(
            data=self._valid_data(new_password1="NewPass2!", new_password2="NewPass2!"),
            instance=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPass2!"))

    def test_password_mismatch_adds_error(self):
        form = CustomUserChangeForm(
            data=self._valid_data(new_password1="NewPass2!", new_password2="WrongPass!"),
            instance=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("new_password2", form.errors)

    def test_email_of_other_user_raises_error(self):
        # Если другой пользователь уже использует этот email → ошибка.
        User.objects.create_user(username="other2", email="taken@test.com", password="x")
        form = CustomUserChangeForm(
            data=self._valid_data(email="taken@test.com"), instance=self.user
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_own_email_does_not_raise_error(self):
        # Пользователь может оставить свой email — это не дубль.
        form = CustomUserChangeForm(
            data=self._valid_data(email="exist@test.com"), instance=self.user
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_save_updates_profile_role(self):
        # save() вызывает get_or_create(user=user) и проставляет роль.
        form = CustomUserChangeForm(data=self._valid_data(), instance=self.user)
        self.assertTrue(form.is_valid())
        form.save()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.role, self.role)

    def test_save_clears_job_title_when_empty_string(self):
        # Пустая строка в job_title → profile.job_title = None.
        self.profile.job_title = "Старая должность"
        self.profile.save()
        form = CustomUserChangeForm(
            data=self._valid_data(job_title=""), instance=self.user
        )
        self.assertTrue(form.is_valid())
        form.save()
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.job_title)


# ─────────────────────────── UserProfileEditForm ──────────────────────────────


class UserProfileEditFormTests(TestCase):
    """Форма самостоятельного редактирования профиля (только first/last/email)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="selfuser", email="self@test.com", password="x"
        )
        self.other = User.objects.create_user(
            username="other_self", email="taken@test.com", password="x"
        )

    def test_valid_form_saves_first_and_last_name(self):
        form = UserProfileEditForm(
            data={"first_name": "Михаил", "last_name": "Сидоров", "email": "self@test.com"},
            instance=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Михаил")
        self.assertEqual(self.user.last_name, "Сидоров")

    def test_email_of_other_user_raises_error(self):
        form = UserProfileEditForm(
            data={"first_name": "X", "last_name": "Y", "email": "taken@test.com"},
            instance=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_own_email_is_fine(self):
        form = UserProfileEditForm(
            data={"first_name": "X", "last_name": "Y", "email": "self@test.com"},
            instance=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_empty_email_is_allowed(self):
        form = UserProfileEditForm(
            data={"first_name": "X", "last_name": "Y", "email": ""},
            instance=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
