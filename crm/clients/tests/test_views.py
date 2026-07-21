# claude
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.test.client import RequestFactory

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.clients.views import ClientSearchView, client_autofill


class ClientAutofillTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        # superuser: user_has_perm пропускает суперюзера на все коды
        self.user = User.objects.create_superuser(
            "staff", "staff@zetom.pl", "pass12345"
        )
        self.person = Client.objects.create(
            first_name="Sigma", last_name="Balls",
            email="email@gmail.com", phone="+48574358039",
        )
        self.company = Company.objects.create(
            name="Sigma Company", nip="5262706346", comments="sigma addr",
        )
        CompanyPersonLink.objects.create(company=self.company, person=self.person)

    def test_search_view_matches_company_name(self):
        request = self.factory.get("/clients/search/", {"q": "Sigma Company"})
        request.user = self.user
        response = ClientSearchView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertTrue(data["results"])
        row = data["results"][0]
        self.assertEqual(row["id"], self.person.id)
        self.assertEqual(row["company_nip"], "5262706346")
        self.assertEqual(row["label"], "Sigma Company")

    def test_client_autofill_by_nip(self):
        request = self.factory.get("/clients/autofill/", {"nip": "5262706346"})
        request.user = self.user
        response = client_autofill(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertTrue(data["exists"])
        self.assertEqual(data["company_name"], "Sigma Company")
        self.assertEqual(data["company_nip"], "5262706346")

    def test_autofill_unknown_nip(self):
        request = self.factory.get("/clients/autofill/", {"nip": "0000000000"})
        request.user = self.user
        response = client_autofill(request)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(json.loads(response.content.decode())["exists"])
