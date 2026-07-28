# claude
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class CompanyCardTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)

    def test_card_renders_company_basics(self):
        from crm.clients.models import Company, SupplierType
        company = Company.objects.create(
            name="Zetom Sp. z o.o.", nip="1234563218", regon="123456785",
            type_supplier=SupplierType.REGIONAL, city="Katowice", email="biuro@zetom.pl",
        )
        url = reverse("admin:clients_company_change", args=[company.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Zetom Sp. z o.o.")
        self.assertContains(resp, "1234563218")
        self.assertContains(resp, "Basic data")       # EN locale (LANGUAGE_CODE=en)
        self.assertContains(resp, "Contact persons")
