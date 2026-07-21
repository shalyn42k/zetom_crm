from django.test import TestCase
from django.test.client import RequestFactory

from crm.clients.models import Client
from crm.clients.views import ClientSearchView, client_autofill


class ClientAutofillTests(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(
            first_name="Sigma",
            last_name="balls",
            company_name="sigma company",
            company_nip="5262706346",
            email="email@gmail.com",
            phone="574358039",
            address="sigma",
        )
        self.factory = RequestFactory()

    def test_search_view_matches_dropdown_label(self):
        q = str(self.client_obj)
        request = self.factory.get("/clients/search/", {"q": q})
        response = ClientSearchView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        data = response.json() if hasattr(response, "json") else __import__("json").loads(response.content.decode())
        self.assertTrue(data["results"])
        self.assertEqual(data["results"][0]["id"], self.client_obj.id)

    def test_client_autofill_by_nip(self):
        request = self.factory.get("/clients/autofill/", {"nip": self.client_obj.company_nip})
        response = client_autofill(request)
        self.assertEqual(response.status_code, 200)
        data = response.json() if hasattr(response, "json") else __import__("json").loads(response.content.decode())
        self.assertTrue(data["exists"])
        self.assertEqual(data["company_name"], self.client_obj.company_name)
