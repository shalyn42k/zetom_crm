# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ на дыры в правах доступа, найденные RBAC-аудитом:
#   • Validation Window (RequestNull) не проверял permission/visibility вообще
#   • dup_request_action / check_duplicates_action не проверяли permission
#
# Важно: post_save-сигнал (crm/users/signals_profile.py) выдаёт КАЖДОМУ
# новому User роль "specialist", а post_migrate-сигнал сеет ей
# view_requests/edit_requests по умолчанию — "юзер вообще без permission"
# в этой системе не бывает просто по факту создания аккаунта. Поэтому два
# разных сценария denial проверяются раздельно:
#   • роль, у которой явно нет нужного permission-кода → 403;
#   • объект вне видимости (не assigned_to, department не пересекается) →
#     get_object_or_404 через visible_requests_for отдаёт 404, как и
#     everywhere else в админке (объект просто не существует для юзера).
#     Раньше видимость вообще не проверялась — значит это было 200 с
#     утечкой чужого лида, а не осмысленный 404.
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from crm.status_manager.services.statuses import RequestStatus
from crm.users.models import Role
from crm.zetom.models import RequestMain, RequestNull

User = get_user_model()

BASE = {
    "first_name": "Jan", "last_name": "Kowalski",
    "phone": "+48501600300", "email": "jan@zetom.pl", "company_name": "Zetom",
}


class SpecialistNoPermMixin:
    """A plain specialist (the auto-assigned default role) whose role has
    had its permissions stripped — isolates the permission-code check from
    the visibility filter. Each test makes its target object visible to
    this user (e.g. via assigned_to) so a 404 from the visibility filter
    can't be mistaken for the 403 this class is actually testing."""

    @classmethod
    def setUpTestData(cls):
        cls.specialist = User.objects.create_user(
            username="specialist_noperm", password="x", is_staff=True,
        )
        # signals_profile.py auto-creates the profile with the shared
        # "specialist" Role (seeded with view_requests/edit_requests by the
        # post_migrate signal) — clearing it here only affects this
        # TestCase's transaction.
        Role.objects.filter(code="specialist").first().permissions.clear()

    def setUp(self):
        self.client.force_login(self.specialist)


class ValidationWindowPermissionTests(SpecialistNoPermMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.rn = RequestNull.objects.create(**BASE)
        self.rn.assigned_to.add(self.specialist)  # visible, isolates the 403

    def _url(self):
        return reverse("admin:zetom_requestnull_validate", args=[self.rn.pk])

    def test_get_forbidden_without_view_requests(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_post_approve_forbidden_without_view_requests(self):
        response = self.client.post(self._url(), {
            "new_first_name": "Jan", "new_last_name": "Kowalski",
            "new_phone": "+48501600300",
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(RequestMain.objects.filter(from_null=self.rn).exists())

    def test_changelist_row_click_forbidden_too(self):
        # RequestNullAdmin.change_view redirects straight to /validate/ —
        # make sure it doesn't let a view_requests-less user through first.
        url = reverse("admin:zetom_requestnull_change", args=[self.rn.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)


class ValidationWindowVisibilityTests(TestCase):
    """Separate class: needs the *default* specialist permissions (view/edit
    requests) intact — only visibility should block access here."""

    @classmethod
    def setUpTestData(cls):
        cls.specialist = User.objects.create_user(
            username="specialist_other_dept", password="x", is_staff=True,
        )

    def setUp(self):
        self.client.force_login(self.specialist)
        # not assigned to this specialist, no department set — invisible to
        # a plain specialist regardless of their (default) permissions.
        self.rn = RequestNull.objects.create(**BASE)

    def test_get_is_404_not_a_data_leak(self):
        # Before the fix, this returned 200 with the lead's PII — visibility
        # (visible_requests_for) wasn't applied to this view at all.
        url = reverse("admin:zetom_requestnull_validate", args=[self.rn.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class DupRequestActionPermissionTests(SpecialistNoPermMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.main = RequestMain.objects.create(**BASE)

    def test_forbidden_without_edit_requests(self):
        url = reverse("admin:zetom_requestmain_dup_request_action")
        response = self.client.post(url, {
            "action": f"delete_existing:main:{self.main.pk}",
        })
        self.assertEqual(response.status_code, 403)
        self.main.refresh_from_db()
        self.assertNotEqual(self.main.status, RequestStatus.cancelled)


class CheckDuplicatesActionPermissionTests(SpecialistNoPermMixin, TestCase):
    def test_forbidden_without_view_requests(self):
        url = reverse("admin:zetom_requestmain_check_duplicates")
        response = self.client.get(url, {"phone": "+48501600300"})
        self.assertEqual(response.status_code, 403)
