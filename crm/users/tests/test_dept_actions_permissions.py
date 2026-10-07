# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТ на дыру в правах доступа, найденную RBAC-аудитом:
#   search_departments_action (crm/users/admin/_dept_actions.py) отдавал
#   список коллег по отделам для произвольного user id без единой проверки
#   permission — в отличие от всех соседних *_department_action методов
#   в том же файле (все они гейтятся _can_edit_departments / view_users).
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from crm.users.models import Role

User = get_user_model()


class SearchDepartmentsPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.target = User.objects.create_user(username="target", password="x")
        cls.stranger = User.objects.create_user(
            username="stranger", password="x", is_staff=True,
        )
        # every new user auto-gets the shared "specialist" Role (seeded with
        # baseline perms by a post_migrate signal) — strip it here so this
        # test actually isolates "no view_users permission".
        Role.objects.filter(code="specialist").first().permissions.clear()

    def setUp(self):
        self.client.force_login(self.stranger)

    def test_forbidden_without_view_users(self):
        url = reverse("admin:auth_user_search_departments", args=[self.target.pk])
        response = self.client.get(url, {"q": "sales"})
        self.assertEqual(response.status_code, 403)
