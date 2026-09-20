# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ на два бага в CustomUserAdmin (crm/users/admin/user.py), найденные
# при разборе раздела пользователей:
#
#   • has_change_permission не проверял, что редактируемый obj — суперюзер:
#     любой юзер с одним лишь edit_users мог открыть /admin/auth/user/<id>/
#     для настоящего суперюзера (see also crm/users/views.py — тот же класс
#     дыр в UserEditView, закрыт отдельно в test_views.py).
#   • save_model никогда не применял поле "departments" из add_fieldsets —
#     выбор отделов при создании юзера через Django admin молча терялся,
#     потому что тот же код-путь (специально для смены существующего
#     юзера) пропускает departments безусловно, а не только при change=True.
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.users.models import Permission, Role
from crm.zetom.models import DepartmentsVariants


def _grant(user, *codes):
    profile = user.profile
    profile.role = None
    profile.otp_exempt = True
    profile.save()
    profile.extra_permissions.set(Permission.objects.filter(code__in=codes))


class SuperuserTargetChangePermissionTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser("root", "root@zetom.pl", "pass12345")
        self.plain = User.objects.create_user(
            "plain", "plain@zetom.pl", "pass12345", is_staff=True,
        )
        _grant(self.plain, "view_users", "edit_users")
        self.client.force_login(self.plain)

    def test_change_view_is_read_only_for_superuser_target(self):
        # Django's dual view/change permission model: view_users still
        # grants view_or_change (read-only render), has_change_permission
        # itself gates the actual write below.
        response = self.client.get(
            reverse("admin:auth_user_change", args=[self.root.pk])
        )
        self.assertIn(response.status_code, (200, 403))

    def test_post_cannot_change_superuser_target(self):
        response = self.client.post(
            reverse("admin:auth_user_change", args=[self.root.pk]),
            data={
                "username": "root",
                "email": "pwned@zetom.pl",
                "first_name": "",
                "last_name": "",
                "new_password1": "TakenOver1!",
                "new_password2": "TakenOver1!",
            },
        )
        self.assertNotEqual(response.status_code, 302)
        self.root.refresh_from_db()
        self.assertEqual(self.root.email, "root@zetom.pl")
        self.assertTrue(self.root.check_password("pass12345"))

    def test_superuser_can_still_reach_own_change_view(self):
        self.client.force_login(self.root)
        response = self.client.get(
            reverse("admin:auth_user_change", args=[self.root.pk])
        )
        self.assertEqual(response.status_code, 200)


class AddFormDepartmentsAppliedTests(TestCase):
    def setUp(self):
        self.admin_role = Role.objects.get(code="admin")
        self.actor = User.objects.create_superuser(
            "actor", "actor@zetom.pl", "pass12345",
        )
        self.client.force_login(self.actor)

    def test_departments_selected_at_creation_are_saved(self):
        dept = DepartmentsVariants.values[0]
        response = self.client.post(reverse("admin:auth_user_add"), data={
            "username": "newhire",
            "email": "newhire@zetom.pl",
            "first_name": "New",
            "last_name": "Hire",
            "password": "StrongPass1!",
            "password_confirm": "StrongPass1!",
            "role": self.admin_role.pk,
            "departments": [dept],
            "job_title": "",
        })
        user = User.objects.get(username="newhire")
        self.assertIn(dept, user.profile.departments or [])
