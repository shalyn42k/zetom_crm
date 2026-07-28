# claude
# Inline client-editor JSON endpoints on RequestMainAdmin (phase 3c).
# Client is person-only since phase 2c: the editor edits person fields;
# company data comes from company_links (Company), never Client.company_*.
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.models import RequestClientLink, RequestMain

_SIMPLE_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def _true(*a, **k):
    return True


@override_settings(STORAGES=_SIMPLE_STATIC)
@patch("crm.zetom.admin.requestmain.user_has_perm", side_effect=_true)
class ClientJsonEndpointsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser("admin", "a@a.com", "x")

    def setUp(self):
        self.client.force_login(self.user)
        self.req = RequestMain.objects.create(
            first_name="Jan", last_name="Kowalski",
            phone="+48501600300", email="jan@zetom.pl",
            company_name="Zetom", company_nip="1234563218",
        )
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski", email="jan@zetom.pl")
        self.company = Company.objects.create(name="Zetom", nip="1234563218")
        CompanyPersonLink.objects.create(company=self.company, person=self.person)
        RequestClientLink.objects.create(request=self.req, client=self.person)

    def test_edit_returns_person_fields_and_company_from_links(self, _p):
        url = reverse("admin:zetom_requestmain_edit_client_json", args=[self.req.pk, self.person.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        d = resp.json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["first_name"], "Jan")
        self.assertEqual(d["last_name"], "Kowalski")
        # company shown from the linked Company (read-only), not Client.company_*
        self.assertEqual(d["company_name"], "Zetom")
        self.assertEqual(d["company_nip"], "1234563218")

    def test_save_updates_person_fields_only(self, _p):
        url = reverse("admin:zetom_requestmain_save_client_json", args=[self.req.pk, self.person.pk])
        resp = self.client.post(url, {
            "first_name": "Anna", "last_name": "Nowak",
            "phone": "+48511222333", "email": "anna@zetom.pl", "address": "ul. Testowa 1",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.person.refresh_from_db()
        self.assertEqual(self.person.first_name, "Anna")
        self.assertEqual(self.person.last_name, "Nowak")
        self.assertEqual(self.person.email, "anna@zetom.pl")
        # the linked Company is untouched by a person save
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "Zetom")

    def test_create_from_request_makes_person_company_and_link(self, _p):
        url = reverse("admin:zetom_requestmain_create_client_json", args=[self.req.pk])
        before = Client.objects.count()
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(Client.objects.count(), before + 1)
        new = Client.objects.latest("created_at")
        # request's company snapshot became a deduped Company + link
        company = Company.objects.get(nip="1234563218")
        self.assertEqual(CompanyPersonLink.objects.filter(company=company, person=new).count(), 1)
        self.assertTrue(RequestClientLink.objects.filter(request=self.req, client=new).exists())
