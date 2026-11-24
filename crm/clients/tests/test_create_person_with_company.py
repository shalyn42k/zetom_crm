# claude
from django.test import TestCase

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.clients.services import create_person_with_company


class CreatePersonWithCompanyTest(TestCase):
    def test_creates_person_and_company_by_nip(self):
        person, company = create_person_with_company(
            first_name="Jan", last_name="Kowalski",
            company_name="Zetom", company_nip="123-456-32-18", email="j@z.pl",
        )
        self.assertIsInstance(person, Client)
        self.assertEqual(person.first_name, "Jan")
        self.assertIsNotNone(company)
        self.assertEqual(company.nip, "1234563218")          # normalized
        self.assertEqual(company.name, "Zetom")
        self.assertEqual(CompanyPersonLink.objects.filter(company=company, person=person).count(), 1)

    def test_dedups_company_by_nip(self):
        c = Company.objects.create(name="Zetom", nip="1234563218")
        person, company = create_person_with_company(
            first_name="A", company_name="Zetom SA", company_nip="1234563218",
        )
        self.assertEqual(company.pk, c.pk)                    # reused, not duplicated
        self.assertEqual(Company.objects.count(), 1)

    def test_company_by_name_when_no_nip(self):
        person, company = create_person_with_company(
            first_name="A", company_name="NoNipCo",
        )
        self.assertIsNotNone(company)
        self.assertEqual(company.name, "NoNipCo")
        self.assertIsNone(company.nip)

    def test_person_only_when_no_company_info(self):
        person, company = create_person_with_company(first_name="Solo", email="s@s.pl")
        self.assertIsNone(company)
        self.assertEqual(CompanyPersonLink.objects.count(), 0)

    def test_invalid_nip_falls_back_to_name(self):
        person, company = create_person_with_company(
            first_name="A", company_name="BadNipCo", company_nip="not-a-nip",
        )
        self.assertIsNotNone(company)
        self.assertEqual(company.name, "BadNipCo")
        self.assertIsNone(company.nip)                        # invalid NIP dropped
