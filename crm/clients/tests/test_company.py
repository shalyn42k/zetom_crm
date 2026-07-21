# claude
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from crm.clients.models import Client, Company, CompanyPersonLink, SupplierType


class CompanyModelTest(TestCase):
    def test_nip_normalized_on_clean(self):
        c = Company(name="Zetom", nip="123-456-32-18")
        c.clean()
        self.assertEqual(c.nip, "1234563218")

    def test_str_shows_name_and_nip(self):
        c = Company.objects.create(name="Zetom", nip="1234563218")
        self.assertEqual(str(c), "Zetom (1234563218)")

    def test_supplier_type_choices(self):
        self.assertEqual(SupplierType.LOCAL, "lokalny")
        self.assertEqual(SupplierType.INTERNATIONAL, "miedzynarodowy")

    # claude
    def test_multiple_blank_nip_companies_allowed(self):
        Company.objects.create(name="Zetom A")
        Company.objects.create(name="Zetom B")
        self.assertEqual(Company.objects.count(), 2)

    # claude
    def test_duplicate_set_nip_raises(self):
        Company.objects.create(name="Zetom A", nip="1234563218")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Company.objects.create(name="Zetom B", nip="1234563218")


class CompanyPersonLinkTest(TestCase):
    def test_link_person_to_company_with_position(self):
        company = Company.objects.create(name="Zetom", nip="1234563218")
        person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        user = User.objects.create(username="staff")
        link = CompanyPersonLink.objects.create(
            company=company, person=person, position="Kierownik",
            is_primary=True, linked_by=user,
        )
        self.assertEqual(person.company_links.count(), 1)
        self.assertEqual(company.person_links.first().position, "Kierownik")
        self.assertTrue(link.is_primary)

    def test_unique_company_person(self):
        from django.db import IntegrityError, transaction
        company = Company.objects.create(name="Zetom")
        person = Client.objects.create(first_name="Jan")
        CompanyPersonLink.objects.create(company=company, person=person)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CompanyPersonLink.objects.create(company=company, person=person)
