# claude
"""Osoby kontaktowe on the Company card: add a person already in the base."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink

User = get_user_model()


class CompanyPersonAttachTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("boss", "b@zetom.pl", "x")
        self.client.force_login(self.user)
        self.company = Company.objects.create(name="Acme")
        self.other = Company.objects.create(name="Beta")
        self.anna = Client.objects.create(first_name="Anna", last_name="Lis", email="anna@beta.pl")
        CompanyPersonLink.objects.create(company=self.other, person=self.anna)
        self.jan = Client.objects.create(first_name="Jan", last_name="Kowalski")
        self.linked = Client.objects.create(first_name="Jan", last_name="Już")
        CompanyPersonLink.objects.create(company=self.company, person=self.linked, is_primary=True)

    def test_search_skips_people_already_linked(self):
        url = reverse("admin:clients_company_person_search", args=[self.company.pk])
        names = [r["name"] for r in self.client.get(url, {"q": "jan"}).json()["results"]]
        self.assertEqual(names, ["Jan Kowalski"])
        anna = self.client.get(url, {"q": "anna"}).json()["results"][0]
        self.assertEqual(anna["company"], "Beta")  # their other company shown as a hint

    def test_attach_existing_person(self):
        url = reverse("admin:clients_company_person_attach", args=[self.company.pk])
        row = self.client.post(url, {"person_id": self.anna.pk, "position": "Księgowa", "is_primary": "1"}).json()["row"]
        link = CompanyPersonLink.objects.get(company=self.company, person=self.anna)
        self.assertEqual(link.position, "Księgowa")
        self.assertTrue(link.is_primary)
        self.assertFalse(CompanyPersonLink.objects.get(company=self.company, person=self.linked).is_primary)
        self.assertEqual(row["email"], "anna@beta.pl")
        self.assertTrue(CompanyPersonLink.objects.filter(company=self.other, person=self.anna).exists())  # still at Beta
        self.assertEqual(Client.objects.count(), 3)  # nobody created

    def test_attach_needs_edit_permission(self):
        from crm.users.models import Role
        u = User.objects.create_user("viewer", "v@zetom.pl", "x", is_staff=True)
        Role.objects.get(code="specialist").permissions.filter(code="edit_clients").delete()
        self.client.force_login(u)
        url = reverse("admin:clients_company_person_attach", args=[self.company.pk])
        self.assertEqual(self.client.post(url, {"person_id": self.jan.pk}).status_code, 403)

    def test_card_offers_both_modes(self):
        html = self.client.get(reverse("admin:clients_company_change", args=[self.company.pk])).content.decode()
        self.assertIn(reverse("admin:clients_company_person_search", args=[self.company.pk]), html)
        self.assertIn("source === 'existing'", html)
