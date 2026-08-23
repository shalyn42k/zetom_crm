# claude — search/autofill handed out Company.comments as the address. That
# field only holds the free-text blob the pre-normalization backfill dumped
# there (migration 0007); the real address lives in street/post_code/city/
# country. Structured fields win, comments stay as the fallback for old rows.
from django.test import TestCase

from crm.clients.models import Company
from crm.clients.views import _company_address


class CompanyAddressTest(TestCase):
    def test_builds_from_structured_fields(self):
        company = Company(
            street="Przemysłowa 12", post_code="30-001", city="Kraków", country="Polska",
        )
        self.assertEqual(
            _company_address(company), "Przemysłowa 12, 30-001 Kraków, Polska",
        )

    def test_skips_blank_parts(self):
        company = Company(street="", post_code="", city="Kraków", country="")
        self.assertEqual(_company_address(company), "Kraków")

    def test_falls_back_to_backfilled_comments(self):
        company = Company(comments="ul. Stara 1, Warszawa")
        self.assertEqual(_company_address(company), "ul. Stara 1, Warszawa")

    def test_structured_fields_beat_comments(self):
        company = Company(city="Kraków", comments="ul. Stara 1, Warszawa")
        self.assertEqual(_company_address(company), "Kraków")

    def test_empty_company_gives_empty_string(self):
        self.assertEqual(_company_address(Company()), "")
