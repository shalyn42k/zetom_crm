# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ на страницу Users > Roles: permissions_display показывает, какие
# права реально даёт каждая роль, прямо в списке — раньше страница
# показывала только code/name, а сами права были не видны нигде в UI.
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.users.models import Permission, Role


class RoleAdminPermissionsDisplayTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_superuser(
            "actor", "actor@zetom.pl", "pass12345",
        )

    def setUp(self):
        self.client.force_login(self.actor)
        self.url = reverse("admin:users_role_changelist")

    def test_lists_every_role_with_its_permission_names(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        specialist = Role.objects.get(code="specialist")
        for perm in specialist.permissions.all():
            self.assertContains(response, perm.name)

    def test_role_with_no_permissions_shows_a_dash(self):
        empty_role, _ = Role.objects.get_or_create(
            code="__tmp_empty_role", defaults={"name": "Empty"},
        )
        empty_role.permissions.clear()
        response = self.client.get(self.url)
        self.assertContains(response, "Empty")
        # the row itself is present and doesn't 500 on an empty M2M
        self.assertEqual(response.status_code, 200)
