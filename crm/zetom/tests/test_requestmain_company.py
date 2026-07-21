# claude
from django.test import TestCase

from crm.clients.models import Company
from crm.zetom.models import RequestMain


class RequestMainCompanyFKTest(TestCase):
    def test_company_fk_nullable(self):
        req = RequestMain.objects.create()
        self.assertIsNone(req.company)

    def test_company_reverse_related_name(self):
        company = Company.objects.create(name="Zetom")
        req = RequestMain.objects.create(company=company)
        self.assertEqual(company.requests.count(), 1)
        self.assertEqual(company.requests.first(), req)
