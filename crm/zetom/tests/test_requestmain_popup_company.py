# claude
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.admin.requestmain import RequestMainAdmin
from crm.zetom.models import RequestClientLink, RequestMain


class RequestMainPopupCompanyTest(TestCase):
    def test_popup_create_new_makes_company_and_links(self):
        admin = RequestMainAdmin(RequestMain, AdminSite())
        user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        obj = RequestMain.objects.create(
            first_name="Jan", last_name="Kowalski",
            company_name="Zetom", company_nip="1234563218",
        )
        rf = RequestFactory()
        req = rf.post("/", {
            "popup_create_new": "1",
            "first_name": "Jan", "last_name": "Kowalski",
            "company_name": "Zetom", "company_nip": "1234563218",
            "phone": "+48501600300", "email": "jan@zetom.pl",
        })
        req.user = user
        # response_add редиректит — нам важны сайд-эффекты
        admin.response_add(req, obj)

        company = Company.objects.get(nip="1234563218")
        obj.refresh_from_db()
        self.assertEqual(obj.company_id, company.pk)
        person = Client.objects.get(first_name="Jan")
        self.assertTrue(RequestClientLink.objects.filter(request=obj, client=person).exists())
        self.assertEqual(CompanyPersonLink.objects.filter(company=company, person=person).count(), 1)
