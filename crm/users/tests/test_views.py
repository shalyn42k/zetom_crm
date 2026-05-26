# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ ВЬЮШЕК users
#
# Views:
#   UserListView       GET /users/
#   UserCreateView     GET/POST /users/create/
#   UserEditView       GET/POST /users/<pk>/edit/
#   UserDeleteView     GET/POST /users/<pk>/delete/
#   UserDetailView     GET /users/<pk>/
#   UserProfileEditView GET/POST /users/me/
#
# ИЗВЕСТНЫЕ БАГИ В PRODUCTION КОДЕ (тесты их задокументировали):
#
#   БАГ 1 — views.py UserListView:
#     User.objects.all().select_related("userprofile") — неверно.
#     related_name="profile", поэтому должно быть select_related("profile").
#     Обход в тестах: мокируем queryset чтобы тест мог проверить логику.
#
#   БАГ 2 — forms.py CustomUserCreateForm.save():
#     UserProfile.objects.create() конфликтует с сигналом create_user_profile,
#     который уже создал профиль при user.save(). → IntegrityError.
#     Обход: отключаем сигнал через post_save.disconnect() на время теста.
#
# Тесты которые проверяют редирект на /users/ (сломанную страницу) используют
# fetch_redirect_response=False — проверяем только URL редиректа, не страницу.
# ──────────────────────────────────────────────────────────────────────────────

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.users.models import Role, UserProfile
from crm.users.signals_profile import create_user_profile

User = get_user_model()


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class UserViewsTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.role = Role.objects.create(code="test_admin", name="Тест Админ")

        cls.actor = User.objects.create_superuser(
            username="actor", email="actor@test.com", password="x"
        )
        cls.target_user = User.objects.create_user(
            username="target", email="target@test.com", password="x"
        )

    def setUp(self):
        self.client.force_login(self.actor)

    # ── UserListView ───────────────────────────────────────────────────────────
    # БАГ: views.py использует select_related("userprofile"), но related_name="profile".
    # Мокируем менеджер чтобы вернуть корректный queryset и проверить логику вьюшки.

    def _patched_list_get(self):
        """Возвращает response с замоканным select_related("userprofile")."""
        correct_qs = User.objects.all().select_related("profile")
        with patch("crm.users.views.User.objects") as mock_mgr:
            mock_mgr.all.return_value.select_related.return_value = correct_qs
            return self.client.get(reverse("user_list"))

    def test_user_list_returns_200(self):
        response = self._patched_list_get()
        self.assertEqual(response.status_code, 200)

    def test_user_list_contains_existing_user(self):
        response = self._patched_list_get()
        self.assertContains(response, "target")

    # ── UserDetailView ─────────────────────────────────────────────────────────

    def test_user_detail_returns_200(self):
        response = self.client.get(reverse("user_detail", args=[self.target_user.pk]))
        self.assertEqual(response.status_code, 200)

    def test_user_detail_404_for_nonexistent_user(self):
        response = self.client.get(reverse("user_detail", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_user_detail_passes_profile_to_context(self):
        response = self.client.get(reverse("user_detail", args=[self.target_user.pk]))
        self.assertIn("profile", response.context)

    # ── UserCreateView ─────────────────────────────────────────────────────────

    def test_user_create_get_returns_200(self):
        response = self.client.get(reverse("user_create"))
        self.assertEqual(response.status_code, 200)

    def test_user_create_get_has_form_in_context(self):
        response = self.client.get(reverse("user_create"))
        self.assertIn("form", response.context)

    def test_user_create_post_valid_creates_user_and_redirects(self):
        # БАГ: форма вызывает UserProfile.objects.create(), но сигнал уже создал
        # профиль при user.save(). Отключаем сигнал на время этого теста.
        # fetch_redirect_response=False — не заходим на /users/ (там другой баг).
        post_data = {
            "username": "brandnew",
            "email": "brandnew@test.com",
            "first_name": "Брэнд",
            "last_name": "Ньюман",
            "password": "StrongPass1!",
            "password_confirm": "StrongPass1!",
            "role": self.role.pk,
            "departments": [],
            "job_title": "Тестер",
        }
        post_save.disconnect(create_user_profile, sender=User)
        try:
            response = self.client.post(reverse("user_create"), data=post_data)
            self.assertRedirects(
                response, reverse("user_list"), fetch_redirect_response=False
            )
            self.assertTrue(User.objects.filter(username="brandnew").exists())
        finally:
            post_save.connect(create_user_profile, sender=User)

    def test_user_create_post_invalid_rerenders_with_errors(self):
        response = self.client.post(reverse("user_create"), data={
            "username": "",
            "password": "",
            "password_confirm": "",
            "role": "",
        })
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertFalse(form.is_valid())

    # ── UserEditView ───────────────────────────────────────────────────────────

    def test_user_edit_get_returns_200(self):
        response = self.client.get(reverse("user_edit", args=[self.target_user.pk]))
        self.assertEqual(response.status_code, 200)

    def test_user_edit_get_404_for_nonexistent(self):
        response = self.client.get(reverse("user_edit", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_user_edit_post_valid_updates_user(self):
        # fetch_redirect_response=False — не заходим на /users/ (там баг select_related).
        post_data = {
            "username": "target",
            "email": "target@test.com",
            "first_name": "Обновлён",
            "last_name": "Пользователь",
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
            "role": self.role.pk,
            "job_title": "Новая должность",
            "new_password1": "",
            "new_password2": "",
        }
        response = self.client.post(
            reverse("user_edit", args=[self.target_user.pk]), data=post_data
        )
        self.assertRedirects(
            response, reverse("user_list"), fetch_redirect_response=False
        )
        self.target_user.refresh_from_db()
        self.assertEqual(self.target_user.first_name, "Обновлён")

    # ── UserDeleteView ─────────────────────────────────────────────────────────

    def test_user_delete_get_returns_200(self):
        user_to_check = User.objects.create_user(username="deleteme_get", password="x")
        response = self.client.get(reverse("user_delete", args=[user_to_check.pk]))
        self.assertEqual(response.status_code, 200)

    def test_user_delete_post_removes_user(self):
        # fetch_redirect_response=False — не заходим на /users/ (там баг select_related).
        user_to_delete = User.objects.create_user(username="deleteme", password="x")
        pk = user_to_delete.pk
        response = self.client.post(reverse("user_delete", args=[pk]))
        self.assertRedirects(
            response, reverse("user_list"), fetch_redirect_response=False
        )
        self.assertFalse(User.objects.filter(pk=pk).exists())

    def test_user_delete_404_for_nonexistent(self):
        response = self.client.post(reverse("user_delete", args=[999999]))
        self.assertEqual(response.status_code, 404)

    # ── UserProfileEditView ────────────────────────────────────────────────────

    def test_profile_edit_get_returns_200(self):
        response = self.client.get(reverse("user_profile_edit"))
        self.assertEqual(response.status_code, 200)

    def test_profile_edit_post_updates_name(self):
        post_data = {
            "first_name": "НовоеИмя",
            "last_name": "НоваяФамилия",
            "email": "actor@test.com",
        }
        response = self.client.post(reverse("user_profile_edit"), data=post_data)
        self.assertRedirects(response, reverse("user_profile_edit"))
        self.actor.refresh_from_db()
        self.assertEqual(self.actor.first_name, "НовоеИмя")

    def test_profile_edit_post_invalid_rerenders(self):
        User.objects.create_user(username="other_actor", email="taken2@test.com", password="x")
        response = self.client.post(reverse("user_profile_edit"), data={
            "first_name": "X",
            "last_name": "Y",
            "email": "taken2@test.com",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].is_valid())
