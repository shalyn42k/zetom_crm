# claude — DepartmentAdmin: access follows the RBAC user permissions (the
# sidebar link is gated on view_users), and ticking / unticking people in
# the form writes UserProfile.departments.
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.users.models import Permission
from crm.zetom.models import Department


def _grant(user, *codes):
    profile = user.profile
    profile.role = None
    profile.otp_exempt = True
    profile.save()
    profile.extra_permissions.set(Permission.objects.filter(code__in=codes))


class DepartmentAdminAccessTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user("viewer", "v@zetom.pl", "pass12345", is_staff=True)
        _grant(self.viewer, "view_users")
        self.editor = User.objects.create_user("editor", "e@zetom.pl", "pass12345", is_staff=True)
        _grant(self.editor, "view_users", "edit_users")
        self.nobody = User.objects.create_user("nobody", "n@zetom.pl", "pass12345", is_staff=True)
        _grant(self.nobody)
        self.dept = Department.objects.get(code="DEPARTMENT_1")

    def test_view_users_can_open_list_but_not_edit(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("admin:zetom_department_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:zetom_department_add")).status_code, 403)

    def test_edit_users_can_add_and_change(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(reverse("admin:zetom_department_add")).status_code, 200)
        url = reverse("admin:zetom_department_change", args=[self.dept.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_without_user_perms_no_access(self):
        self.client.force_login(self.nobody)
        self.assertEqual(self.client.get(reverse("admin:zetom_department_changelist")).status_code, 403)

    def test_only_superuser_deletes(self):
        self.client.force_login(self.editor)
        url = reverse("admin:zetom_department_delete", args=[self.dept.pk])
        self.assertEqual(self.client.get(url).status_code, 403)


class DepartmentAdminMembershipTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser("root", "root@zetom.pl", "pass12345")
        self.root.profile.otp_exempt = True
        self.root.profile.save()
        self.client.force_login(self.root)
        self.alice = User.objects.create_user("alice", "a@zetom.pl", "pass12345")
        self.bob = User.objects.create_user("bob", "b@zetom.pl", "pass12345")

    def test_new_department_gets_code_and_members(self):
        response = self.client.post(reverse("admin:zetom_department_add"), {
            "name": "Quality Lab", "users": [self.alice.pk],
        })
        self.assertEqual(response.status_code, 302)
        dept = Department.objects.get(name="Quality Lab")
        self.assertEqual(dept.code, f"DEPARTMENT_{dept.pk}")
        self.alice.profile.refresh_from_db()
        self.assertIn(dept.code, self.alice.profile.departments)

    def test_unticking_removes_code_from_all_profile_lists(self):
        dept = Department.objects.get(code="DEPARTMENT_2")
        profile = self.bob.profile
        profile.departments = [dept.code]
        profile.main_departments = [dept.code]
        profile.head_of_departments = [dept.code]
        profile.save()
        self.client.post(reverse("admin:zetom_department_change", args=[dept.pk]), {
            "name": dept.name, "users": [],
        })
        profile.refresh_from_db()
        self.assertEqual(
            (profile.departments, profile.main_departments, profile.head_of_departments),
            ([], [], []),
        )
