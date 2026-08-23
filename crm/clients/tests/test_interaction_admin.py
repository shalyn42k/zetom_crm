# claude — ClientInteractionAdmin still searched client__company_name, a column
# migration 0009 dropped, so every search in that changelist raised FieldError.
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.clients.models import (
    Client, ClientInteraction, Company, CompanyPersonLink,
)


class InteractionSearchTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        company = Company.objects.create(name="Zetom Sp.", nip="1234563218")
        CompanyPersonLink.objects.create(company=company, person=person)
        ClientInteraction.objects.create(
            client=person, channel=ClientInteraction.Channel.CALL,
            summary="Rozmowa o ofercie", contacted_at=timezone.now(),
        )

    def _search(self, term):
        return self.client.get(
            reverse("admin:clients_clientinteraction_changelist"),
            {"q": term},
            HTTP_HOST="127.0.0.1",
        )

    # claude — summary isn't in list_display, so assert on the changelist's
    # result_count rather than on rendered text.
    def test_search_by_person_name(self):
        resp = self._search("Kowalski")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["cl"].result_count, 1)

    # claude — company name is now reached through the CompanyPersonLink M2M.
    def test_search_by_company_name(self):
        resp = self._search("Zetom")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["cl"].result_count, 1)

    def test_search_by_summary(self):
        resp = self._search("ofercie")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["cl"].result_count, 1)

    def test_search_with_no_match_does_not_error(self):
        resp = self._search("nieistniejaca-firma")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["cl"].result_count, 0)
