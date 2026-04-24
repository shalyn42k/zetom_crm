from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from crm.zetom.models import Oferta, RequestMain, RequestNull, Wniosek, Zlecenie
from crm.zetom.services.statuses import Status


BASE_DATA = {
    "phone": "+48501600300",
    "company_name": "Zetom Sp. z o.o.",
    "email": "contact@zetom.pl",
    "company_nip": "7322215365",
}


def always_true(*args, **kwargs):
    return True


@patch("crm.zetom.admin.user_has_perm", side_effect=always_true)
class ApproveNullAdminActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username="admin", email="a@a.com", password="x"
        )

    def setUp(self):
        self.client.force_login(self.user)

    @patch("crm.zetom.admin.send_notification_approve_null")
    def test_approve_action_creates_main_and_redirects(
        self, send_mock, _perm_mock
    ):
        null = RequestNull.objects.create(**BASE_DATA)
        url = reverse("admin:zetom_requestnull_approve_action", args=[null.pk])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(RequestMain.objects.count(), 1)
        main = RequestMain.objects.first()
        self.assertEqual(main.company_nip, null.company_nip)
        send_mock.assert_called_once_with(main)


@patch("crm.zetom.admin.user_has_perm", side_effect=always_true)
class MainAdminActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username="admin", email="a@a.com", password="x"
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.main = RequestMain.objects.create(**BASE_DATA)

    def test_oferta_action_creates_oferta(self, _):
        url = reverse(
            "admin:zetom_requestmain_oferta_action", args=[self.main.pk]
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Oferta.objects.filter(from_main=self.main).count(), 1)

    def test_zlecenie_action_creates_zlecenie(self, _):
        url = reverse(
            "admin:zetom_requestmain_zlecenie_action", args=[self.main.pk]
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Zlecenie.objects.filter(from_main=self.main).count(), 1)

    def test_wniosek_action_creates_wniosek(self, _):
        url = reverse(
            "admin:zetom_requestmain_wniosek_action", args=[self.main.pk]
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Wniosek.objects.filter(from_main=self.main).count(), 1)


@patch("crm.zetom.admin.user_has_perm", side_effect=always_true)
class ChildSaveModelTests(TestCase):
    """Covers save_model delegating to save_child_with_status in child admins."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username="admin", email="a@a.com", password="x"
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.main = RequestMain.objects.create(**BASE_DATA)
        self.oferta = Oferta.objects.create(**BASE_DATA, from_main=self.main)

    def _change_url(self):
        return reverse("admin:zetom_oferta_change", args=[self.oferta.pk])

    def _form_data(self, status):
        return {
            **BASE_DATA,
            "from_main": self.main.pk,
            "status": status,
            "price": "0",
            "notes": "",
            "department": "DEPARTMENT_0",
        }

    def test_valid_transition_saved(self, _):
        response = self.client.post(
            self._change_url(), data=self._form_data(Status.in_progress)
        )
        self.assertIn(response.status_code, (302, 200))
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.in_progress)

    def test_invalid_transition_keeps_previous_status(self, _):
        # new → waiting is not allowed; status should stay at `new`
        self.client.post(self._change_url(), data=self._form_data(Status.waiting))
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.new)
