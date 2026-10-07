# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ visible_requests_for — видимость заявок по ролям.
#
# Фикс (DOCS/rbac.md §7.3): department_head раньше видел/мог редактировать
# ВСЕ отделы (ничем не отличался от auditor по видимости). Теперь — только
# head_of_departments + личные назначения (как у specialist).
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.test import TestCase

from crm.users.models import Role
from crm.zetom.models import DepartmentsVariants, RequestMain
from crm.zetom.services.visibility import visible_requests_for

User = get_user_model()

BASE = {"phone": "+48501600300", "email": "jan@zetom.pl"}


class DepartmentHeadVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.head = User.objects.create_user(username="dep_head1", password="x")
        profile = cls.head.profile
        profile.role = Role.objects.get(code="department_head")
        profile.departments = [DepartmentsVariants.DEPARTMENT_1]
        profile.head_of_departments = [DepartmentsVariants.DEPARTMENT_1]
        profile.save()

    def test_sees_requests_in_own_department(self):
        own = RequestMain.objects.create(
            **BASE, departments=[DepartmentsVariants.DEPARTMENT_1],
        )
        visible = visible_requests_for(self.head, RequestMain.objects.all())
        self.assertIn(own, visible)

    def test_does_not_see_requests_in_other_departments(self):
        # before the fix: department_head fell through to the "sees
        # everything" branch, same as admin/auditor/all_seeing.
        other = RequestMain.objects.create(
            **BASE, departments=[DepartmentsVariants.DEPARTMENT_3],
        )
        visible = visible_requests_for(self.head, RequestMain.objects.all())
        self.assertNotIn(other, visible)

    def test_sees_personally_assigned_request_outside_own_department(self):
        # mirrors specialist's "personal assignment" fallback — a dep_head
        # isn't blind to a Req assigned to them personally outside the
        # department(s) they head.
        other = RequestMain.objects.create(
            **BASE, departments=[DepartmentsVariants.DEPARTMENT_3],
        )
        other.assigned_to.add(self.head)
        visible = visible_requests_for(self.head, RequestMain.objects.all())
        self.assertIn(other, visible)

    def test_dep_head_with_no_head_of_departments_sees_only_personal(self):
        headless = User.objects.create_user(username="dep_head_noscope", password="x")
        profile = headless.profile
        profile.role = Role.objects.get(code="department_head")
        profile.save()

        assigned = RequestMain.objects.create(**BASE)
        assigned.assigned_to.add(headless)
        unrelated = RequestMain.objects.create(**BASE)

        visible = visible_requests_for(headless, RequestMain.objects.all())
        self.assertIn(assigned, visible)
        self.assertNotIn(unrelated, visible)


class AuditorVisibilityUnchangedTests(TestCase):
    """auditor stays global/read-only visibility — not part of this fix."""

    def test_auditor_sees_every_department(self):
        auditor = User.objects.create_user(username="auditor1", password="x")
        profile = auditor.profile
        profile.role = Role.objects.get(code="auditor")
        profile.save()

        req = RequestMain.objects.create(
            **BASE, departments=[DepartmentsVariants.DEPARTMENT_5],
        )
        visible = visible_requests_for(auditor, RequestMain.objects.all())
        self.assertIn(req, visible)
