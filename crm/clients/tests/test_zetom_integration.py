# claude — cross-module contract between clients and zetom. The clients cards
# and the request admin write to the same Company/Client rows from opposite
# ends, so these check that each side survives what the other does.
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.clients.models import (
    Client, ClientInteraction, Company, CompanyPersonLink,
)
from crm.clients.services import create_person_with_company
from crm.zetom.models import RequestMain

BASE_REQ = {
    "first_name": "Jan",
    "last_name": "Kowalski",
    "phone": "+48501600300",
    "email": "jan@zetom.pl",
    "company_name": "Zetom",
}


class DeleteCascadeTest(TestCase):
    """Deleting from the clients side must not take zetom rows with it."""

    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.company = Company.objects.create(name="Zetom", nip="1234563218")
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        CompanyPersonLink.objects.create(company=self.company, person=self.person)
        self.request_main = RequestMain.objects.create(**BASE_REQ, company=self.company)
        self.request_main.clients.add(self.person)

    # claude — RequestMain.company is SET_NULL: a firm can be removed from the
    # base without destroying its request history.
    def test_deleting_company_keeps_requests(self):
        self.client.post(
            reverse("admin:clients_company_delete", args=[self.company.pk]),
            {"post": "yes"}, HTTP_HOST="127.0.0.1",
        )
        self.request_main.refresh_from_db()
        self.assertIsNone(self.request_main.company_id)
        self.assertTrue(Client.objects.filter(pk=self.person.pk).exists())
        self.assertFalse(CompanyPersonLink.objects.exists())

    def test_deleting_person_keeps_requests(self):
        self.client.post(
            reverse("admin:clients_client_delete", args=[self.person.pk]),
            {"post": "yes"}, HTTP_HOST="127.0.0.1",
        )
        self.assertTrue(RequestMain.objects.filter(pk=self.request_main.pk).exists())


class IntakeCompatibilityTest(TestCase):
    """Rows the zetom intake creates must stay editable on the clients cards."""

    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)

    # claude — the intake used to store a NIP after normalizing it but without
    # checking the checksum, so firms carrying a typo'd NIP are already in the
    # DB. Built directly here (bypassing validation) because that is exactly
    # what those rows are: data that predates the guard. Their card must stay
    # savable, or an old typo locks a panel the user cannot fix.
    def test_legacy_bad_checksum_nip_can_still_be_saved(self):
        company = Company.objects.create(name="Zetom", nip="1234563219")
        resp = self.client.post(
            reverse("admin:clients_company_save", args=[company.pk]),
            {
                "section": "podstawowe", "name": "Zetom S.A.",
                "nip": company.nip, "regon": "", "type_supplier": "",
            },
            HTTP_HOST="127.0.0.1",
        )
        self.assertTrue(resp.json()["ok"])
        company.refresh_from_db()
        self.assertEqual(company.name, "Zetom S.A.")
        self.assertEqual(company.nip, "1234563219")  # left as it was

    # claude — but touching the NIP means accepting the check.
    def test_changing_a_nip_is_still_validated(self):
        company = Company.objects.create(name="Zetom", nip="1234563219")
        resp = self.client.post(
            reverse("admin:clients_company_save", args=[company.pk]),
            {
                "section": "podstawowe", "name": "Zetom",
                # checksum digit for 526270634… is 7, so 0 is rejected
                "nip": "5262706340", "regon": "", "type_supplier": "",
            },
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 400)
        company.refresh_from_db()
        self.assertEqual(company.nip, "1234563219")

    # claude — and no new ones get in: a bad-checksum NIP would create a firm
    # that no later NIP lookup could ever match, so the firm is deduped by name
    # instead. The typed value is not lost — it stays on the request's own
    # company_nip snapshot, which is where the operator entered it.
    def test_intake_drops_a_bad_checksum_nip(self):
        request_main = RequestMain.objects.create(
            **{**BASE_REQ, "company_nip": "1234563219"},
        )
        _person, company = create_person_with_company(
            first_name="Jan", last_name="Kowalski",
            company_name=request_main.company_name,
            company_nip=request_main.company_nip,
        )
        self.assertIsNone(company.nip)
        self.assertEqual(company.name, "Zetom")
        self.assertEqual(request_main.company_nip, "1234563219")

    def test_intake_keeps_a_valid_nip(self):
        _person, company = create_person_with_company(
            first_name="Jan", company_name="Zetom", company_nip="123-456-32-18",
        )
        self.assertEqual(company.nip, "1234563218")

    def test_intake_company_appears_on_the_klienci_list(self):
        create_person_with_company(
            first_name="Jan", last_name="Kowalski",
            company_name="Zetom", company_nip="1234563218",
        )
        resp = self.client.get(
            reverse("admin:clients_client_changelist"), HTTP_HOST="127.0.0.1",
        )
        rows = resp.context["rows"]
        # the firm shows up; the person is its contact, not a standalone row
        self.assertEqual([(r["kind"], r["nazwa"]) for r in rows], [("company", "Zetom")])


class CardRenderTest(TestCase):
    """Both cards render with real zetom data attached."""

    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.company = Company.objects.create(name="Zetom", nip="1234563218")
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        CompanyPersonLink.objects.create(company=self.company, person=self.person)
        self.request_main = RequestMain.objects.create(**BASE_REQ, company=self.company)
        self.request_main.clients.add(self.person)
        ClientInteraction.objects.create(
            client=self.person, channel=ClientInteraction.Channel.CALL,
            summary="Rozmowa", contacted_at=timezone.now(), request=self.request_main,
        )

    def test_company_card_shows_request_and_history(self):
        resp = self.client.get(
            reverse("admin:clients_company_change", args=[self.company.pk]),
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["zgloszenia"]), 1)
        self.assertEqual(len(resp.context["historia"]), 1)

    def test_person_card_shows_request_and_history(self):
        resp = self.client.get(
            reverse("admin:clients_client_change", args=[self.person.pk]),
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["zgloszenia"]), 1)
        self.assertEqual(len(resp.context["historia"]), 1)

    # claude — ClientInteraction and CompanyPersonLink both autocomplete across
    # the module boundary; each needs the target admin's search_fields intact.
    def test_cross_model_autocompletes(self):
        cases = [
            ("clientinteraction", "client"),
            ("clientinteraction", "request"),
            ("companypersonlink", "person"),
        ]
        for model_name, field_name in cases:
            with self.subTest(field=f"{model_name}.{field_name}"):
                resp = self.client.get(
                    "/admin/autocomplete/",
                    {
                        "app_label": "clients", "model_name": model_name,
                        "field_name": field_name, "term": "Zeto",
                    },
                    HTTP_HOST="127.0.0.1",
                )
                self.assertEqual(resp.status_code, 200)
                self.assertIn("results", resp.json())
