# claude
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.clients.models import (
    Client, ClientInteraction, Company, CompanyPersonLink,
)
from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import DepartmentsVariants, RequestMain


class CompanyCardPanelsTest(TestCase):
    """Phase 3a Task 3: Powiązane zgłoszenia + Historia kontaktów panels
    must render real RequestMain/ClientInteraction rows, not the Task 1/2
    empty scaffolds."""

    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.company = Company.objects.create(name="Zetom Sp. z o.o.", nip="1234563218")
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        CompanyPersonLink.objects.create(
            company=self.company, person=self.person, position="Kierownik",
        )

    def test_requests_and_history_panels_render_real_data(self):
        request_main = RequestMain.objects.create(
            phone="+48501600300", email="jan@zetom.pl",
            company=self.company, status=RequestStatus.active,
            departments=[DepartmentsVariants.DEPARTMENT_1],
        )
        ClientInteraction.objects.create(
            client=self.person,
            channel=ClientInteraction.Channel.CALL,
            summary="Rozmowa o ofercie kalibracji",
            contacted_by=self.user,
            contact_person="Jan Kowalski",
            contacted_at=timezone.now(),
            request=request_main,
        )

        url = reverse("admin:clients_company_change", args=[self.company.pk])
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Related requests")   # EN locale (LANGUAGE_CODE=en)
        self.assertContains(resp, "Contact history")
        self.assertContains(resp, f"Request no. {request_main.pk}")
        self.assertContains(resp, "Rozmowa o ofercie kalibracji")

    def test_unrelated_company_history_not_leaked(self):
        # A ClientInteraction for a person of another firm must not show up
        # on this company's card (regression guard for the M2M filter).
        other_company = Company.objects.create(name="Other Sp.")
        other_person = Client.objects.create(first_name="Anna")
        CompanyPersonLink.objects.create(company=other_company, person=other_person)
        ClientInteraction.objects.create(
            client=other_person,
            channel=ClientInteraction.Channel.EMAIL,
            summary="Nie powinno się tu pojawić",
            contacted_at=timezone.now(),
        )

        url = reverse("admin:clients_company_change", args=[self.company.pk])
        resp = self.client.get(url)

        self.assertNotContains(resp, "Nie powinno się tu pojawić")
