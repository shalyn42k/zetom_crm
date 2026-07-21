# claude
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.admin.requestmain import RequestMainAdmin
from crm.zetom.models import RequestMain


class PrefillFromCompanyTest(TestCase):
    def test_prefill_pulls_company_from_link(self):
        person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        company = Company.objects.create(name="Zetom", nip="1234563218")
        CompanyPersonLink.objects.create(company=company, person=person)

        admin = RequestMainAdmin(RequestMain, AdminSite())
        rf = RequestFactory()
        req = rf.get("/add/", {"client": str(person.pk)})
        req.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")

        initial = admin.get_changeform_initial_data(req)
        self.assertEqual(initial["first_name"], "Jan")
        self.assertEqual(initial["company_name"], "Zetom")
        self.assertEqual(initial["company_nip"], "1234563218")
