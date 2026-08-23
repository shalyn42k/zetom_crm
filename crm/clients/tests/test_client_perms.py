# claude — the Person card gated itself on has_change_permission (edit_clients)
# while the Company card next door used has_view_permission, so a read-only
# user could open a firm but got PermissionDenied on a person. Both are read
# surfaces — every write control on them sits behind its own can_edit check.
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company
from crm.users.models import Permission


class ViewOnlyAccessTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "viewer", "v@v.pl", "pass12345", is_staff=True,
        )
        profile = self.user.profile
        profile.otp_exempt = True
        # claude — drop the role the RBAC signal hands new users: its default
        # set already carries edit_clients, which would mask the read-only case
        # this test is about. effective_permissions() then reads extras only.
        profile.role = None
        profile.save()
        profile.extra_permissions.add(Permission.objects.get(code="view_clients"))
        self.client.force_login(self.user)
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        self.company = Company.objects.create(name="Zetom")

    def test_can_open_person_card(self):
        resp = self.client.get(
            reverse("admin:clients_client_change", args=[self.person.pk]),
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 200)

    def test_can_open_company_card(self):
        resp = self.client.get(
            reverse("admin:clients_company_change", args=[self.company.pk]),
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 200)

    def test_can_open_list(self):
        resp = self.client.get(
            reverse("admin:clients_client_changelist"), HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 200)

    # claude — read-only means read-only: no edit affordances rendered, and the
    # write endpoints reject the same user outright.
    def test_person_card_hides_edit_controls(self):
        resp = self.client.get(
            reverse("admin:clients_client_change", args=[self.person.pk]),
            HTTP_HOST="127.0.0.1",
        )
        self.assertNotContains(resp, "edit-btn")

    def test_write_endpoints_forbidden(self):
        urls = [
            reverse("admin:clients_client_person_save", args=[self.person.pk]),
            reverse("admin:clients_company_save", args=[self.company.pk]),
            reverse("admin:clients_client_attach_company", args=[self.person.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                resp = self.client.post(url, {}, HTTP_HOST="127.0.0.1")
                self.assertEqual(resp.status_code, 403)
