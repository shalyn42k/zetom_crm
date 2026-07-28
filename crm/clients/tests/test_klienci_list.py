# claude
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink


class KlienciListTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.firma = Company.objects.create(name="Zetom Sp.", nip="1234563218")
        self.osoba = Client.objects.create(first_name="Jan", last_name="Prywatny")  # no links = private
        linked = Client.objects.create(first_name="Anna", last_name="Kontakt")
        CompanyPersonLink.objects.create(company=self.firma, person=linked)  # contact, not private

    def _get(self, **params):
        return self.client.get(reverse("admin:clients_client_changelist"), params, HTTP_HOST="127.0.0.1")

    def test_list_shows_company_and_private_person(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Zetom Sp.")       # firma
        self.assertContains(resp, "Jan Prywatny")     # private person
        self.assertContains(resp, "Private person")  # EN locale (LANGUAGE_CODE=en)

    def test_filter_firmy_only(self):
        resp = self._get(rodzaj="firmy")
        self.assertContains(resp, "Zetom Sp.")
        self.assertNotContains(resp, "Jan Prywatny")

    def test_filter_osoby_only(self):
        resp = self._get(rodzaj="osoby")
        self.assertContains(resp, "Jan Prywatny")
        self.assertNotContains(resp, "Zetom Sp.")
