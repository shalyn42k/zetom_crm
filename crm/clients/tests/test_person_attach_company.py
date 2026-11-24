# claude
# Phase 3c: attach an existing person to another Company from the Person card
# (Firmy panel). Two endpoints on ClientAdmin.get_urls: company search (picker)
# and attach (creates a CompanyPersonLink).
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink


class PersonAttachCompanyTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        self.c_linked = Company.objects.create(name="AlreadyLinked", nip="1234563218")
        self.c_free = Company.objects.create(name="Zetom Sp.", nip="5262706346")
        CompanyPersonLink.objects.create(company=self.c_linked, person=self.person)

    def test_search_excludes_already_linked(self):
        url = reverse("admin:clients_client_company_search", args=[self.person.pk])
        resp = self.client.get(url, {"q": "e"}, HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 200)
        names = {r["name"] for r in resp.json()["results"]}
        self.assertIn("Zetom Sp.", names)
        self.assertNotIn("AlreadyLinked", names)  # already linked → excluded

    def test_attach_creates_link(self):
        url = reverse("admin:clients_client_attach_company", args=[self.person.pk])
        resp = self.client.post(url, {"company_id": self.c_free.pk}, HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(
            CompanyPersonLink.objects.filter(company=self.c_free, person=self.person).count(), 1
        )

    def test_attach_is_idempotent(self):
        url = reverse("admin:clients_client_attach_company", args=[self.person.pk])
        self.client.post(url, {"company_id": self.c_free.pk}, HTTP_HOST="127.0.0.1")
        self.client.post(url, {"company_id": self.c_free.pk}, HTTP_HOST="127.0.0.1")
        self.assertEqual(
            CompanyPersonLink.objects.filter(company=self.c_free, person=self.person).count(), 1
        )
