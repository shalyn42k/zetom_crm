# claude — the Firmy panel on the Person card could only attach: there was no
# way to change stanowisko/główny kontakt or to undo a wrong attach.
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink


class CompanyLinkOpsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        self.company = Company.objects.create(name="Zetom")
        self.link = CompanyPersonLink.objects.create(
            company=self.company, person=self.person, position="Specjalista",
        )

    def test_save_updates_position_and_primary(self):
        url = reverse(
            "admin:clients_client_company_link_save", args=[self.person.pk, self.link.pk],
        )
        resp = self.client.post(
            url, {"position": "Kierownik", "is_primary": "1"}, HTTP_HOST="127.0.0.1",
        )
        self.assertTrue(resp.json()["ok"])
        self.link.refresh_from_db()
        self.assertEqual(self.link.position, "Kierownik")
        self.assertTrue(self.link.is_primary)

    # claude — "główny kontakt" is per-Company: setting it must demote the
    # other contacts of THAT company, not the person's other companies.
    def test_primary_is_exclusive_within_company(self):
        other_person = Client.objects.create(first_name="Anna", last_name="Nowak")
        other_link = CompanyPersonLink.objects.create(
            company=self.company, person=other_person, is_primary=True,
        )
        url = reverse(
            "admin:clients_client_company_link_save", args=[self.person.pk, self.link.pk],
        )
        self.client.post(url, {"position": "", "is_primary": "1"}, HTTP_HOST="127.0.0.1")
        other_link.refresh_from_db()
        self.link.refresh_from_db()
        self.assertTrue(self.link.is_primary)
        self.assertFalse(other_link.is_primary)

    def test_primary_in_another_company_is_left_alone(self):
        second_company = Company.objects.create(name="Inna")
        second_link = CompanyPersonLink.objects.create(
            company=second_company, person=self.person, is_primary=True,
        )
        url = reverse(
            "admin:clients_client_company_link_save", args=[self.person.pk, self.link.pk],
        )
        self.client.post(url, {"position": "", "is_primary": "1"}, HTTP_HOST="127.0.0.1")
        second_link.refresh_from_db()
        self.assertTrue(second_link.is_primary)

    def test_detach_drops_link_only(self):
        url = reverse(
            "admin:clients_client_company_link_detach", args=[self.person.pk, self.link.pk],
        )
        resp = self.client.post(url, HTTP_HOST="127.0.0.1")
        self.assertTrue(resp.json()["ok"])
        self.assertFalse(CompanyPersonLink.objects.filter(pk=self.link.pk).exists())
        # neither side of the link is deleted
        self.assertTrue(Client.objects.filter(pk=self.person.pk).exists())
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())

    # claude — pk in the URL scopes the link; another person's link must 404
    # rather than be editable through this person's endpoint.
    def test_cannot_touch_another_persons_link(self):
        stranger = Client.objects.create(first_name="Obcy")
        stranger_link = CompanyPersonLink.objects.create(
            company=self.company, person=stranger,
        )
        url = reverse(
            "admin:clients_client_company_link_detach",
            args=[self.person.pk, stranger_link.pk],
        )
        resp = self.client.post(url, HTTP_HOST="127.0.0.1")
        self.assertTrue(CompanyPersonLink.objects.filter(pk=stranger_link.pk).exists())
        self.assertEqual(resp.status_code, 200)  # no-op delete, nothing matched

    def test_card_renders_link_controls(self):
        resp = self.client.get(
            reverse("admin:clients_client_change", args=[self.person.pk]),
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(resp, f"openEdit({self.link.pk}")
        self.assertContains(resp, f"detach({self.link.pk})")
