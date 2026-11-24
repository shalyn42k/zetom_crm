# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ utils.py — user_has_perm()
#
# user_has_perm(user, perm) — кастомная проверка разрешений через Role.
# Не использует стандартные Django permissions — проверяет наличие
# Permission.code в permissions M2M роли пользователя.
#
# Ветки которые тестируем:
#   1. Не аутентифицирован → False
#   2. is_superuser=True → True (без проверки роли)
#   3. Нет профиля → False
#   4. Профиль есть, роли нет → False
#   5. Роль есть, нужного пермишена нет → False
#   6. Роль есть, нужный пермишен есть → True
# ──────────────────────────────────────────────────────────────────────────────

from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase

from crm.users.models import Permission, Role, UserProfile
from crm.users.utils import user_has_perm

User = get_user_model()


class UserHasPermTests(TestCase):

    def setUp(self):
        # Используем test__* коды — RBAC сигнал уже создал view_users и другие стандартные.
        self.perm = Permission.objects.create(code="test__view_u", name="Тест просмотр")
        self.role = Role.objects.create(code="test__manager", name="Тест Менеджер")
        self.role.permissions.add(self.perm)

        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="x"
        )

    def test_unauthenticated_user_returns_false(self):
        # Создаём mock-объект, у которого is_authenticated=False.
        # Это проще чем AnonymousUser — не нужна сессия.
        anon = MagicMock()
        anon.is_authenticated = False
        self.assertFalse(user_has_perm(anon, "view_users"))

    def test_superuser_returns_true_for_any_perm(self):
        # is_superuser=True — функция возвращает True сразу, не смотрит на роль.
        self.user.is_superuser = True
        self.user.save()
        self.assertTrue(user_has_perm(self.user, "view_users"))
        self.assertTrue(user_has_perm(self.user, "nonexistent_perm"))

    def test_user_without_profile_returns_false(self):
        # getattr(user, 'profile', None) вернёт None → функция вернёт False.
        # Удаляем профиль созданный сигналом.
        self.user.profile.delete()
        # После удаления профиля refresh — чтобы кэш атрибутов сбросился.
        self.user = User.objects.get(pk=self.user.pk)
        self.assertFalse(user_has_perm(self.user, "view_users"))

    def test_user_with_profile_but_no_role_returns_false(self):
        # Профиль есть, но role=None → функция вернёт False.
        profile = self.user.profile
        profile.role = None
        profile.save()
        self.assertFalse(user_has_perm(self.user, "view_users"))

    def test_user_with_role_without_permission_returns_false(self):
        # Роль есть, но нужного пермишена нет.
        role_no_perms = Role.objects.create(code="test__viewer", name="Тест Читатель")
        self.user.profile.role = role_no_perms
        self.user.profile.save()
        self.assertFalse(user_has_perm(self.user, "test__view_u"))

    def test_user_with_role_with_permission_returns_true(self):
        # Роль есть, пермишен есть → True.
        self.user.profile.role = self.role
        self.user.profile.save()
        self.assertTrue(user_has_perm(self.user, "test__view_u"))

    def test_user_with_role_returns_false_for_missing_perm_code(self):
        # Пермишен с таким кодом вообще не существует в роли.
        self.user.profile.role = self.role
        self.user.profile.save()
        self.assertFalse(user_has_perm(self.user, "test__nonexistent_perm"))
