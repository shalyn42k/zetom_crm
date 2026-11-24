# claude
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink


class CompanyContactsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.company = Company.objects.create(name="Zetom", nip="1234563218")

    def test_add_contact_creates_person_and_link(self):
        url = reverse("admin:clients_company_person_add", args=[self.company.pk])
        resp = self.client.post(url, {
            "first_name": "Jan", "last_name": "Kowalski",
            "email": "j@z.pl", "phone": "+48501600300",
            "position": "Kierownik", "is_primary": "1",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        link = CompanyPersonLink.objects.get(company=self.company)
        self.assertEqual(link.person.first_name, "Jan")
        self.assertEqual(link.position, "Kierownik")
        self.assertTrue(link.is_primary)

    def test_delete_contact_removes_link_keeps_person(self):
        person = Client.objects.create(first_name="Jan")
        link = CompanyPersonLink.objects.create(company=self.company, person=person)
        url = reverse("admin:clients_company_person_delete", args=[self.company.pk, link.pk])
        resp = self.client.post(url)
        self.assertTrue(resp.json()["ok"])
        self.assertFalse(CompanyPersonLink.objects.filter(pk=link.pk).exists())
        self.assertTrue(Client.objects.filter(pk=person.pk).exists())  # person kept
