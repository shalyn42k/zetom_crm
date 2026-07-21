# claude
from django.test import TestCase

from crm.clients.backfill import backfill_companies
from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.models import RequestClientLink, RequestMain


def _run():
    backfill_companies(Client, Company, CompanyPersonLink, RequestMain, RequestClientLink)


class BackfillTest(TestCase):
    def test_creates_company_from_client_nip(self):
        Client.objects.create(
            first_name="Jan", last_name="Kowalski",
            company_name="Zetom", company_nip="1234563218",
        )
        _run()
        self.assertEqual(Company.objects.count(), 1)
        company = Company.objects.get()
        self.assertEqual(company.name, "Zetom")
        self.assertEqual(company.nip, "1234563218")
        self.assertEqual(CompanyPersonLink.objects.count(), 1)

    def test_dedup_same_nip_two_people(self):
        Client.objects.create(first_name="A", company_name="Zetom", company_nip="1234563218")
        Client.objects.create(first_name="B", company_name="Zetom SA", company_nip="123-456-32-18")
        _run()
        self.assertEqual(Company.objects.count(), 1)          # один NIP → одна фирма
        self.assertEqual(CompanyPersonLink.objects.count(), 2)  # оба привязаны

    def test_person_without_company_skipped(self):
        Client.objects.create(first_name="Solo")  # ни name ни nip
        _run()
        self.assertEqual(Company.objects.count(), 0)
        self.assertEqual(CompanyPersonLink.objects.count(), 0)

    def test_sets_requestmain_company(self):
        client = Client.objects.create(company_name="Zetom", company_nip="1234563218")
        req = RequestMain.objects.create()
        RequestClientLink.objects.create(request=req, client=client)
        _run()
        req.refresh_from_db()
        self.assertEqual(req.company, Company.objects.get())

    def test_idempotent(self):
        Client.objects.create(company_name="Zetom", company_nip="1234563218")
        _run()
        _run()
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(CompanyPersonLink.objects.count(), 1)

    def test_duplicate_company_name_no_crash(self):
        # Два клиента с разными валидными по формату NIP → две разные фирмы
        # "Zetom" (дедуп по NIP). Третий клиент без NIP уходит в name-ветку,
        # где name="Zetom" уже неоднозначен (две записи Company).
        Client.objects.create(first_name="A", company_name="Zetom", company_nip="1234567890")
        Client.objects.create(first_name="B", company_name="Zetom", company_nip="1111111111")
        Client.objects.create(first_name="C", company_name="Zetom")
        _run()
        self.assertEqual(Company.objects.filter(name__iexact="Zetom").count(), 2)
        self.assertEqual(CompanyPersonLink.objects.count(), 3)
