# claude
from django.test import TestCase

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.models import RequestNull
from crm.zetom.services.duplicate_matcher import (
    BADGE_SAME_COMPANY, BADGE_SAME_NIP, find_candidates,
)


def _person_in_company(nip="1234567890", name="Zetom", **person):
    company = Company.objects.create(name=name, nip=nip)
    client = Client.objects.create(**person)
    CompanyPersonLink.objects.create(company=company, person=client)
    return client


class DuplicateMatcherCompanyAwareTest(TestCase):
    def test_same_nip_from_linked_company(self):
        _person_in_company(nip="1234567890", first_name="Jan", last_name="Kowalski")
        rn = RequestNull.objects.create(
            first_name="X", last_name="Y", company_nip="1234567890",
        )
        results = find_candidates(rn)
        self.assertTrue(results)
        self.assertIn(BADGE_SAME_NIP, [b.kind for b in results[0].badges])

    def test_same_company_name_from_linked_company(self):
        _person_in_company(nip="", name="Zetom", first_name="Jan", last_name="Kowalski")
        rn = RequestNull.objects.create(
            first_name="X", last_name="Y", company_name="Zetom",
        )
        results = find_candidates(rn)
        self.assertTrue(results)
        self.assertIn(BADGE_SAME_COMPANY, [b.kind for b in results[0].badges])

    def test_person_without_company_gets_no_nip_badge(self):
        Client.objects.create(first_name="Solo", last_name="NoCompany")
        rn = RequestNull.objects.create(
            first_name="Solo", last_name="NoCompany", company_nip="1234567890",
        )
        results = find_candidates(rn)
        for c in results:
            self.assertNotIn(BADGE_SAME_NIP, [b.kind for b in c.badges])

    def test_nip_only_prefilter_catches_candidate(self):
        # человек без совпадений по phone/email/name, только NIP через фирму
        _person_in_company(nip="9999999999", first_name="Zzz", last_name="Qqq")
        rn = RequestNull.objects.create(
            first_name="Aaa", last_name="Bbb", company_nip="9999999999",
        )
        results = find_candidates(rn)
        self.assertTrue(results)  # найден по NIP фирмы, хотя имя/контакты разные
