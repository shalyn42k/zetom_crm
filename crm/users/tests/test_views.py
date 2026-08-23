# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ ВЬЮШЕК users
#
# Views:
#   UserListView       GET /users/
#   UserCreateView     GET/POST /users/create/
#   UserEditView       GET/POST /users/<pk>/edit/
#   UserDeactivateView GET/POST /users/<pk>/delete/
#   UserDetailView     GET /users/<pk>/
#   UserProfileEditView GET/POST /users/me/
#
# ИЗВЕСТНЫЕ БАГИ В PRODUCTION КОДЕ (тесты их задокументировали):
#
#   БАГ 1 — ИСПРАВЛЕН (claude): views.py UserListView использовал
#     select_related("userprofile") при related_name="profile" и падал с
#     FieldError на каждом запросе. Обход с моком менеджера убран.
#
#   БАГ 2 — forms.py CustomUserCreateForm.save():
#     UserProfile.objects.create() конфликтует с сигналом create_user_profile,
#     который уже создал профиль при user.save(). → IntegrityError.
#     Обход: отключаем сигнал через post_save.disconnect() на время теста.
#
# claude — все вьюшки этого модуля теперь за RBAC-гейтом, поэтому тесты
# логинятся под юзером с нужными правами. Проверки самого гейта (аноним,
# нехватка прав, попытка эскалации) лежат в UsersUIAccessTests ниже.
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.users.models import Permission, Role, UserProfile
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

    def test_user_list_returns_200(self):
        response = self.client.get(reverse("user_list"))
        self.assertEqual(response.status_code, 200)

    def test_user_list_contains_existing_user(self):
        response = self.client.get(reverse("user_list"))
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

    # ── UserDeactivateView ─────────────────────────────────────────────────────
    # claude — вьюшка раньше делала user.delete(). Теперь деактивация: юзер
    # остаётся в базе вместе с ролью и историей, но теряет доступ.

    def test_user_deactivate_get_returns_200(self):
        user_to_check = User.objects.create_user(username="dropme_get", password="x")
        response = self.client.get(reverse("user_deactivate", args=[user_to_check.pk]))
        self.assertEqual(response.status_code, 200)

    def test_user_deactivate_post_keeps_row_and_revokes_access(self):
        target = User.objects.create_user(username="dropme", password="x")
        response = self.client.post(reverse("user_deactivate", args=[target.pk]))
        self.assertRedirects(response, reverse("user_list"))

        target.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=target.pk).exists())
        self.assertFalse(target.is_active)

    def test_user_deactivate_404_for_nonexistent(self):
        response = self.client.post(reverse("user_deactivate", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_deactivate_self(self):
        self.client.post(reverse("user_deactivate", args=[self.actor.pk]))
        self.actor.refresh_from_db()
        self.assertTrue(self.actor.is_active)

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


# claude — регрессия на дыру, найденную 2026-08-23: весь users_ui был
# набором голых `View` без единой проверки доступа. Анонимный POST на
# /users/<pk>/delete/ удалял любого юзера, а POST на /users/<pk>/edit/ с
# is_superuser=1 выдавал полные права — шаблон рендерит форму циклом по
# всем полям, включая привилегированные. CSRF не защищал: токен приезжал
# на том же анонимном GET.
class UsersUIAccessTests(TestCase):

    def setUp(self):
        self.victim = User.objects.create_user(
            username="victim", email="victim@test.com", password="x",
        )
        self.plain = User.objects.create_user(
            username="plain", email="plain@test.com", password="x", is_staff=True,
        )
        profile = self.plain.profile
        profile.role = None
        profile.otp_exempt = True
        profile.save()

    def _write_urls(self):
        return [
            reverse("user_create"),
            reverse("user_edit", args=[self.victim.pk]),
            reverse("user_deactivate", args=[self.victim.pk]),
        ]

    def _read_urls(self):
        return [reverse("user_list"), reverse("user_detail", args=[self.victim.pk])]

    def test_anonymous_is_redirected_to_login(self):
        for url in self._read_urls() + self._write_urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertNotIn(url, response["Location"].split("?")[0])

    def test_anonymous_cannot_deactivate(self):
        url = reverse("user_deactivate", args=[self.victim.pk])
        self.client.post(url)
        self.victim.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=self.victim.pk).exists())
        self.assertTrue(self.victim.is_active)

    def test_anonymous_cannot_create_accounts(self):
        self.client.post(reverse("user_create"), data={
            "username": "backdoor",
            "email": "backdoor@test.com",
            "password": "StrongPass1!",
            "password_confirm": "StrongPass1!",
        })
        self.assertFalse(User.objects.filter(username="backdoor").exists())

    def test_staff_without_permissions_gets_403(self):
        self.client.force_login(self.plain)
        for url in self._read_urls() + self._write_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_view_users_alone_does_not_grant_write(self):
        self.plain.profile.extra_permissions.set(
            Permission.objects.filter(code="view_users")
        )
        self.client.force_login(self.plain)

        self.assertEqual(self.client.get(reverse("user_list")).status_code, 200)
        for url in self._write_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    # claude — edit_users правит профильные поля, но не раздаёт власть:
    # is_superuser и role остаются за суперюзером / `edit_roles`.
    def test_edit_users_cannot_escalate_to_superuser(self):
        self.plain.profile.extra_permissions.set(
            Permission.objects.filter(code__in=["view_users", "edit_users"])
        )
        self.client.force_login(self.plain)

        self.client.post(reverse("user_edit", args=[self.victim.pk]), data={
            "username": "victim",
            "email": "victim@test.com",
            "first_name": "Nice",
            "last_name": "Try",
            "is_superuser": True,
            "is_staff": True,
            "is_active": True,
            "new_password1": "",
            "new_password2": "",
        })

        self.victim.refresh_from_db()
        self.assertFalse(self.victim.is_superuser)
        self.assertFalse(self.victim.is_staff)
        self.assertEqual(self.victim.first_name, "Nice")

    def test_edit_users_cannot_assign_privileged_role(self):
        admin_role = Role.objects.get(code="admin")
        self.plain.profile.extra_permissions.set(
            Permission.objects.filter(
                code__in=["view_users", "edit_users", "edit_roles"]
            )
        )
        self.client.force_login(self.plain)

        self.client.post(reverse("user_edit", args=[self.victim.pk]), data={
            "username": "victim",
            "email": "victim@test.com",
            "first_name": "",
            "last_name": "",
            "role": admin_role.pk,
            "new_password1": "",
            "new_password2": "",
        })

        self.victim.profile.refresh_from_db()
        self.assertNotEqual(self.victim.profile.role, admin_role)
