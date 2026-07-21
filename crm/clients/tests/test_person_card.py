# claude
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink


class PersonCardTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)

    def test_card_shows_person_and_firmy(self):
        person = Client.objects.create(first_name="Jan", last_name="Kowalski", email="j@z.pl")
        company = Company.objects.create(name="Zetom", nip="1234563218")
        CompanyPersonLink.objects.create(company=company, person=person, position="Kierownik")
        resp = self.client.get(reverse("admin:clients_client_change", args=[person.pk]), HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Jan")
        self.assertContains(resp, "Dane osobowe")
        self.assertContains(resp, "Firmy")
        self.assertContains(resp, "Zetom")
        self.assertContains(resp, "Kierownik")

    def test_person_save_updates_fields(self):
        person = Client.objects.create(first_name="Old")
        url = reverse("admin:clients_client_person_save", args=[person.pk])
        resp = self.client.post(url, {"first_name": "New", "last_name": "Name", "email": "n@n.pl"}, HTTP_HOST="127.0.0.1")
        self.assertTrue(resp.json()["ok"])
        person.refresh_from_db()
        self.assertEqual(person.first_name, "New")
