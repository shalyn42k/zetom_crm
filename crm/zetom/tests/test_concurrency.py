# claude — two people editing the same record (crm/zetom/admin/concurrency.py)
# and approving the same lead twice (requestnull_validate.validation_window_view).
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.zetom.models import Department, Oferta, RequestMain, RequestNull
from crm.zetom.services.request_service import approve_null_action

_SIMPLE_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
TOKEN_RE = re.compile(r'name="_concurrency_token" value="([^"]+)"')


def _card_post_data(main, **overrides):
    data = {
        "first_name": main.first_name or "",
        "last_name": main.last_name or "",
        "company_name": main.company_name or "",
        "company_nip": main.company_nip or "",
        "email": main.email,
        "phone": str(main.phone),
        "address": main.address or "",
        "message": main.message or "",
    }
    data.update(overrides)
    return data


@override_settings(STORAGES=_SIMPLE_STATIC)
class RequestCardOptimisticLockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_superuser("alice", "alice@zetom.pl", "x")
        cls.bob = User.objects.create_superuser("bob", "bob@zetom.pl", "x", first_name="Bob")

    def setUp(self):
        self.main = RequestMain.objects.create(
            phone="+48501600300", email="old@zetom.pl", first_name="Jan",
        )
        self.url = reverse("admin:zetom_requestmain_change", args=[self.main.pk])

    def _token_for(self, user):
        self.client.force_login(user)
        match = TOKEN_RE.search(self.client.get(self.url).content.decode())
        self.assertIsNotNone(match, "change page must render the token")
        return match.group(1)

    def test_stale_save_is_refused_and_keeps_the_other_users_change(self):
        alice_token = self._token_for(self.alice)
        bob_token = self._token_for(self.bob)

        # Bob saves first.
        r = self.client.post(self.url, _card_post_data(
            self.main, email="bob@client.pl", _concurrency_token=bob_token,
        ))
        self.assertEqual(r.status_code, 302)

        # Alice saves from the page she opened before Bob's save.
        self.client.force_login(self.alice)
        r = self.client.post(self.url, _card_post_data(
            self.main, first_name="Janusz", _concurrency_token=alice_token,
        ))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Bob")
        self.main.refresh_from_db()
        self.assertEqual(self.main.email, "bob@client.pl")
        self.assertEqual(self.main.first_name, "Jan")

        # The re-rendered page carries the fresh token: saving again is a
        # deliberate overwrite.
        fresh = TOKEN_RE.search(r.content.decode()).group(1)
        self.assertNotEqual(fresh, alice_token)
        r = self.client.post(self.url, _card_post_data(
            self.main, first_name="Janusz", _concurrency_token=fresh,
        ))
        self.assertEqual(r.status_code, 302)
        self.main.refresh_from_db()
        self.assertEqual(self.main.first_name, "Janusz")

    def test_save_without_token_still_works(self):
        self.client.force_login(self.alice)
        r = self.client.post(self.url, _card_post_data(self.main, first_name="Adam"))
        self.assertEqual(r.status_code, 302)
        self.main.refresh_from_db()
        self.assertEqual(self.main.first_name, "Adam")

    def test_document_window_renders_token(self):
        oferta = Oferta.objects.create(
            from_main=self.main, phone="+48501600300", email="old@zetom.pl",
        )
        self.client.force_login(self.alice)
        r = self.client.get(reverse("admin:zetom_oferta_change", args=[oferta.pk]))
        self.assertRegex(r.content.decode(), TOKEN_RE)


@override_settings(STORAGES=_SIMPLE_STATIC)
class DoubleApproveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("admin", "a@a.pl", "x")

    @patch("crm.zetom.admin.requestnull_validate.send_notification_approve_null")
    def test_second_approve_of_the_same_lead_does_not_overwrite_the_first(self, _mail):
        dept = Department.objects.create(name="Lab")
        lead = RequestNull.objects.create(phone="+48501600300", email="lead@zetom.pl")
        stale = RequestNull.objects.get(pk=lead.pk)  # page opened by the 2nd person
        first = approve_null_action(lead.pk)        # 1st person approved meanwhile
        first.departments = ["DEPARTMENT_0"]
        first.save()

        self.client.force_login(self.user)
        url = reverse("admin:zetom_requestnull_validate", args=[lead.pk])
        with patch(
            "crm.zetom.admin.requestnull_validate.get_object_or_404", return_value=stale,
        ):
            r = self.client.post(url, {"departments": [dept.code], "owners": [self.user.pk]})

        self.assertRedirects(
            r, reverse("admin:zetom_requestmain_change", args=[first.pk]),
            fetch_redirect_response=False,
        )
        first.refresh_from_db()
        self.assertEqual(first.departments, ["DEPARTMENT_0"])
        self.assertEqual(RequestMain.objects.count(), 1)
